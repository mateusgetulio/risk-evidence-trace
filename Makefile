PY := .venv/bin/python

.PHONY: setup test lint denylist

setup:
	python3 -m venv .venv
	$(PY) -m pip install -r requirements-dev.txt

test:
	$(PY) -m pytest

lint:
	.venv/bin/ruff check .
	.venv/bin/mypy packages/decision/src

denylist:
	sh scripts/check_denylist.sh
