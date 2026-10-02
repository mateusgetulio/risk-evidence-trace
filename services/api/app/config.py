from __future__ import annotations

import os
from pathlib import Path


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "postgresql+psycopg://rte:rte@localhost:5433/rte")


def demo_mode() -> bool:
    return os.environ.get("DEMO_MODE") == "1"


def fixtures_dir() -> Path:
    configured = os.environ.get("FIXTURES_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3] / "fixtures"


def carrier_url() -> str:
    return os.environ.get("CARRIER_URL", "http://localhost:8000/carrier")


def carrier_client_timeout() -> float:
    return float(os.environ.get("CARRIER_CLIENT_TIMEOUT", "2.0"))


def carrier_stall_seconds() -> float:
    return float(os.environ.get("CARRIER_STALL_SECONDS", "3.5"))


def carrier_retry_delay_seconds() -> float:
    return float(os.environ.get("CARRIER_RETRY_DELAY_SECONDS", "60"))


def carrier_default_mode() -> str:
    return os.environ.get("CARRIER_MODE", "ok")
