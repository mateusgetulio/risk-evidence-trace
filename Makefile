PY := .venv/bin/python
export PYTHONPATH := packages/decision/src:services/api

.PHONY: setup db test lint denylist seed

setup:
	python3 -m venv .venv
	$(PY) -m pip install -r requirements-dev.txt

db:
	docker compose up -d --wait db

test:
ifndef CI
	$(MAKE) db
endif
	$(PY) -m pytest

lint:
	.venv/bin/ruff check .
	.venv/bin/mypy packages/decision/src

denylist:
	sh scripts/check_denylist.sh

seed: db
	$(PY) -m app.seed
