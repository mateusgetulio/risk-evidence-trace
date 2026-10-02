PY := .venv/bin/python
export PYTHONPATH := packages/decision/src:services/api

.PHONY: setup test lint web-check denylist plain-text check check-local seed local-seed local-api local-worker local-web

setup:
	python3 -m venv .venv
	$(PY) -m pip install -r requirements-dev.txt
	cd apps/web && npm ci

test:
	$(PY) -m pytest

lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .
	.venv/bin/mypy packages/decision/src

web-check:
	cd apps/web && npx tsc --noEmit && npx eslint .

denylist:
	sh scripts/check_denylist.sh

plain-text:
	sh scripts/check_plain_text.sh

check: lint test web-check plain-text

check-local: check denylist

seed:
	docker compose exec api python -m app.seed

local-seed:
	DEMO_MODE=1 $(PY) -m app.seed

local-api:
	DEMO_MODE=1 CARRIER_MODE=timeout_once $(PY) -m uvicorn app.main:app --port 8000

local-worker:
	$(PY) -m app.worker

local-web:
	cd apps/web && npm run dev
