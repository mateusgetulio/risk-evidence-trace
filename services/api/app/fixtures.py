from __future__ import annotations

import json
import re
from typing import Any

from app.config import fixtures_dir

NAME_PATTERN = re.compile(r"^[a-z0-9_]+$")


class UnknownFixtureError(ValueError):
    pass


def fixture_names() -> list[str]:
    return sorted(path.stem for path in fixtures_dir().glob("*.json"))


def load_fixture(name: str) -> dict[str, Any]:
    if not NAME_PATTERN.match(name) or name not in fixture_names():
        raise UnknownFixtureError(f"unknown fixture: {name}")
    loaded: dict[str, Any] = json.loads((fixtures_dir() / f"{name}.json").read_text())
    return loaded
