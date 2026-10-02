from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from app.main import create_app
from app.seed import seed
from app.worker import run_until_idle
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

SUBMISSION_QUERY = """
query ($id: Int!) {
  submission(id: $id) {
    companyName primaryDomain pendingJobs
    observations { id source claim value stale supersededBy ageSeconds }
    decision {
      outcome totalPoints previousOutcome
      contributions { ruleId points observationId changed ruleText missingEvidence }
      blockers { observationId }
      superseded { observationId supersededBy }
    }
  }
}
"""


@pytest.fixture
def client(engine: Engine) -> TestClient:
    return TestClient(create_app(engine))


def run(client: TestClient, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    response = client.post("/graphql", json={"query": query, "variables": variables or {}})
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def test_submission_query_returns_evidence_and_the_traced_decision(
    client: TestClient, engine: Engine
) -> None:
    acme = seed(engine)["acme.test"]
    body = run(client, SUBMISSION_QUERY, {"id": acme})
    assert "errors" not in body
    submission = body["data"]["submission"]
    assert submission["companyName"] == "Acme Manufacturing"
    assert submission["decision"]["outcome"] == "QUOTE"
    assert submission["decision"]["totalPoints"] == -5
    contribution = submission["decision"]["contributions"][0]
    assert contribution["ruleId"] == "BK-02"
    assert contribution["ruleText"]
    ids = {o["id"] for o in submission["observations"]}
    assert contribution["observationId"] in ids
    superseded = {o["id"]: o["supersededBy"] for o in submission["observations"]}
    assert sum(1 for v in superseded.values() if v is not None) == 1


def test_deliver_fixture_mutation_flips_the_decision_and_marks_changed_rows(
    client: TestClient, engine: Engine
) -> None:
    acme = seed(engine)["acme.test"]
    mutation = """
    mutation ($id: Int!, $fixture: String!) {
      deliverFixture(submissionId: $id, fixture: $fixture) { newObservations clockAdvanced }
    }
    """
    body = run(client, mutation, {"id": acme, "fixture": "acme_late_scan"})
    assert body["data"]["deliverFixture"] == {"newObservations": 2, "clockAdvanced": False}

    pending = run(client, SUBMISSION_QUERY, {"id": acme})["data"]["submission"]
    assert pending["pendingJobs"] == 1
    assert pending["decision"]["outcome"] == "QUOTE"

    run_until_idle(engine)
    after = run(client, SUBMISSION_QUERY, {"id": acme})["data"]["submission"]
    assert after["pendingJobs"] == 0
    decision = after["decision"]
    assert (decision["outcome"], decision["previousOutcome"]) == ("REFER", "QUOTE")
    changed = [c["ruleId"] for c in decision["contributions"] if c["changed"]]
    assert changed == ["EX-01"]
    assert len(decision["superseded"]) == 2


def test_unknown_fixture_returns_a_graphql_error(client: TestClient, engine: Engine) -> None:
    acme = seed(engine)["acme.test"]
    body = run(
        client,
        'mutation ($id: Int!) { deliverFixture(submissionId: $id, fixture: "nope") '
        "{ newObservations } }",
        {"id": acme},
    )
    assert body["errors"][0]["message"] == "unknown fixture: nope"


def test_decision_trace_as_of_recomputes_without_storing_a_run(
    client: TestClient, engine: Engine
) -> None:
    acme = seed(engine)["acme.test"]
    with engine.connect() as conn:
        origin = conn.execute(
            text("SELECT clock_origin FROM submissions WHERE id = :id"), {"id": acme}
        ).scalar_one()
        before = conn.execute(text("SELECT count(*) FROM decision_runs")).scalar_one()
    query = """
    query ($id: Int!, $asOf: DateTime) {
      decisionTrace(submissionId: $id, asOf: $asOf) {
        runId outcome totalPoints inputHash
        contributions { ruleId }
        blockers { observationId }
      }
    }
    """
    now = run(client, query, {"id": acme, "asOf": origin.isoformat()})["data"]["decisionTrace"]
    later_at = (origin + timedelta(days=6)).isoformat()
    later = run(client, query, {"id": acme, "asOf": later_at})["data"]["decisionTrace"]
    stored = run(client, query, {"id": acme})["data"]["decisionTrace"]

    assert now["runId"] is None and later["runId"] is None and stored["runId"] is not None
    assert (now["outcome"], now["totalPoints"]) == ("QUOTE", -5)
    assert (later["outcome"], later["totalPoints"]) == ("REFER", 10)
    assert [c["ruleId"] for c in later["contributions"]] == ["BK-01"]
    assert len(later["blockers"]) == 1
    assert now["inputHash"] != later["inputHash"]
    assert (
        now["inputHash"]
        == run(client, query, {"id": acme, "asOf": origin.isoformat()})["data"]["decisionTrace"][
            "inputHash"
        ]
    )
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM decision_runs")).scalar_one() == before


def test_timeline_is_newest_first_with_plain_english_messages(
    client: TestClient, engine: Engine
) -> None:
    acme = seed(engine)["acme.test"]
    body = run(
        client,
        "query ($id: Int!) { timeline(submissionId: $id) { kind message } }",
        {"id": acme},
    )
    events = body["data"]["timeline"]
    assert events[0]["kind"] == "decision_computed"
    assert events[0]["message"] == "First decision: QUOTE with -5 points."
    assert "\u2014" not in "".join(e["message"] for e in events)


def test_reset_demo_is_refused_outside_demo_mode(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEMO_MODE", raising=False)
    body = run(client, "mutation { resetDemo { submissionIds } }")
    assert "DEMO_MODE=1" in body["errors"][0]["message"]


def test_reset_demo_reseeds_in_demo_mode(
    client: TestClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_MODE", "1")
    acme = seed(engine)["acme.test"]
    run(
        client,
        'mutation ($id: Int!) { deliverFixture(submissionId: $id, fixture: "acme_late_scan") '
        "{ newObservations } }",
        {"id": acme},
    )
    body = run(client, "mutation { resetDemo { submissionIds } }")
    assert body["data"]["resetDemo"]["submissionIds"] == [1, 2]
    after = run(client, SUBMISSION_QUERY, {"id": 1})["data"]["submission"]
    assert after["decision"]["outcome"] == "QUOTE"
    assert len(after["observations"]) == 3
