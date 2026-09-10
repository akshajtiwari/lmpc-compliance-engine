-include .env
export

PYTHON := .venv/bin/python
ALEMBIC := .venv/bin/alembic
UVICORN := .venv/bin/uvicorn
LOCAL_DB_URL := postgresql+psycopg://lmpc:lmpc_local@127.0.0.1:54329/lmpc
LMPC_DB_URL ?= $(LOCAL_DB_URL)
LMPC_OFFICER_UUID ?= 00000000-0000-4000-8000-000000000002
LMPC_JURISDICTION_UUID ?= 00000000-0000-4000-8000-000000000001

.PHONY: setup db-up db-down migrate bootstrap dev test test-db

setup:
	python -m venv .venv
	$(PYTHON) -m pip install -r requirements.txt -r requirements-server.txt

db-up:
	docker compose up -d --wait postgres

db-down:
	docker compose down

migrate: db-up
	$(ALEMBIC) upgrade head

bootstrap: migrate
	$(PYTHON) -m lmpc.server.db.bootstrap

dev: bootstrap
	$(UVICORN) lmpc.server.main:app --reload --reload-dir lmpc --host 127.0.0.1 --port 8000

test:
	$(PYTHON) -m pytest -q
	$(PYTHON) -m stress.run
	$(PYTHON) -m stress.campaign

test-db: bootstrap
	LMPC_TEST_DB_URL=$(LMPC_DB_URL) $(PYTHON) -m pytest tests/test_db_integration.py -q
