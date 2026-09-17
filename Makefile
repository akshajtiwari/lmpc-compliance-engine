-include .env
export

PYTHON := .venv/bin/python
ALEMBIC := .venv/bin/alembic
UVICORN := .venv/bin/uvicorn
LOCAL_DB_URL := postgresql+psycopg://lmpc:lmpc_local@127.0.0.1:54329/lmpc
LMPC_DB_URL ?= $(LOCAL_DB_URL)
LMPC_OFFICER_UUID ?= 00000000-0000-4000-8000-000000000002
LMPC_JURISDICTION_UUID ?= 00000000-0000-4000-8000-000000000001
LMPC_LOAD_BASE_URL ?= http://127.0.0.1:8000
LMPC_LOAD_EMAIL ?= $(LMPC_BOOTSTRAP_EMAIL)
LMPC_LOAD_PASSWORD ?= $(LMPC_BOOTSTRAP_PASSWORD)

DESKTOP_DEV_DATA := $(CURDIR)/.lmpc-data/desktop

.PHONY: setup db-up db-down migrate bootstrap dev dev-lan dev-desktop dev-app \
	addresses desktop-reset test test-db load-smoke

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

dev-lan: bootstrap
	$(PYTHON) -m lmpc.server.run --lan --reload --port 8000

# The portable build, from source. Same code path as LMPC-Compliance.exe — SQLite store,
# pairing page, QR — with no PyInstaller step, so a pairing or scan change is testable in
# seconds instead of a release build. Phone connections are allowed from the start and
# the store is kept inside the repo, so this is a development target, not the shipped
# default. `make desktop-reset` throws the store away to retest first-run.
dev-desktop:
	LMPC_DESKTOP_DATA_DIR=$(DESKTOP_DEV_DATA) \
		$(PYTHON) -m lmpc.desktop --no-browser --allow-phones --port 8000

# Which addresses a phone could actually dial, and why the rest were passed over.
# Run this first when a phone says it cannot reach the server.
addresses:
	$(PYTHON) -m lmpc.desktop --addresses

desktop-reset:
	rm -rf $(DESKTOP_DEV_DATA)

# The Field app over Metro, on a phone running Expo Go — no APK build. The QR scanner
# reads the code off the camera, so pairing works here exactly as it does in a release
# build. Keep the phone on the same Wi-Fi as this machine.
dev-app:
	cd apps/mobile && npx expo start

test:
	$(PYTHON) -m pytest -q
	$(PYTHON) -m stress.run
	$(PYTHON) -m stress.campaign

test-db: bootstrap
	LMPC_TEST_DB_URL=$(LMPC_DB_URL) $(PYTHON) -m pytest tests/test_db_integration.py -q

load-smoke:
	docker run --rm --network host -v "$(CURDIR):/work" -w /work \
		-e LMPC_LOAD_BASE_URL -e LMPC_LOAD_EMAIL -e LMPC_LOAD_PASSWORD \
		-e LMPC_LOAD_VUS=2 -e LMPC_LOAD_RAMP=2s -e LMPC_LOAD_HOLD=15s \
		grafana/k6:1.7.1 run stress/load/inspection.js
