const CONTRIBUTION_FIELDS = `
  ruleId points observationId reason missingEvidence ruleText changed
`;

export const PAGE_QUERY = `
query Page($id: Int!) {
  submission(id: $id) {
    id companyName primaryDomain status asOf pendingJobs
    observations {
      id source sourceObservationId subject claim value observedAt ageSeconds stale supersededBy
    }
    decision {
      runId asOf inputHash outcome totalPoints previousOutcome previousPoints
      contributions { ${CONTRIBUTION_FIELDS} }
      removed { ${CONTRIBUTION_FIELDS} }
      blockers { kind observationId reason }
      superseded { observationId supersededBy }
    }
    transmission { id state attempts idempotencyKey lastError acknowledgementId }
  }
  timeline(submissionId: $id) { id at kind message }
}
`;

export const DELIVER_FIXTURE = `
mutation DeliverFixture($id: Int!, $fixture: String!) {
  deliverFixture(submissionId: $id, fixture: $fixture) { newObservations clockAdvanced }
}
`;

export const RESET_DEMO = `
mutation ResetDemo { resetDemo { submissionIds } }
`;

export const SEND_TO_CARRIER = `
mutation SendToCarrier($id: Int!) {
  sendToCarrier(submissionId: $id) { transmissionId state queued replay }
}
`;
