# Comandi del progetto. `make help` li elenca.
SHELL := /bin/bash
PY := .venv/bin/python
# COMPOSE_EXTRA=-f compose.sessione.yaml nelle sessioni cloud dietro proxy.
COMPOSE := BUILDX_BAKE_ENTITLEMENTS_FS=0 docker compose -f compose.yaml $(COMPOSE_EXTRA)
LIMITE ?=
SONDA ?=

.PHONY: help setup env up down init test lint collect test-integration create-user telegram-login eval

help:
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*## "}{printf "  %-18s %s\n", $$1, $$2}'

setup: ## Ambiente Python locale per test e lint
	python3.12 -m venv .venv && .venv/bin/pip install -q -U pip && .venv/bin/pip install -q -e '.[dev]'

env: ## Crea .env con segreti casuali, se non esiste
	@test -f .env && echo ".env esiste già" || $(PY) -m core.envfile

up: ## Avvia database, archivio, portale, lavoratore e raccolta
	$(COMPOSE) up -d --build

down: ## Ferma tutto (i dati restano nei volumi)
	$(COMPOSE) down

init: ## Migrazioni, ruolo di raccolta, secchi dell'archivio
	$(COMPOSE) run --rm init

test: ## Test unitari: solo fixture, nessuna rete. Serve `docker compose up -d db`
	$(PY) -m pytest

lint: ## Formattazione e controlli statici
	$(PY) -m ruff check . && $(PY) -m ruff format --check .

collect: ## Esegue una sonda su dati reali nel suo contenitore: make collect SONDA=snapshot LIMITE=3
	@test -n "$(SONDA)" || { echo "Indica la sonda: SONDA=snapshot|adm"; exit 1; }
	@[[ "$(LIMITE)" =~ ^[1-9][0-9]*$$ ]] || { echo "Indica un limite esplicito: LIMITE=<n>"; exit 1; }
	$(COMPOSE) run --rm init python -m core.cli accoda-sonda $(SONDA)
	$(COMPOSE) run --rm raccolta python -m probes.runner --sonda $(SONDA) --limite $(LIMITE)

test-integration: ## Prova su dati reali: URL in PROVA_URLS (al massimo tre) → snapshot → confronto ADM
	$(COMPOSE) up -d --build db archivio lavoratore
	$(COMPOSE) run --rm init python -m tests.integration.prepara
	$(COMPOSE) run --rm raccolta python -m probes.runner --sonda snapshot --limite 3
	$(COMPOSE) run --rm init python -m pytest -m integration tests/integration -q

create-user: ## Crea un account del portale: make create-user UTENTE=nome RUOLO=amministratore
	@test -n "$(UTENTE)" || { echo "Indica UTENTE=<nome>"; exit 1; }
	$(COMPOSE) run --rm init python -m core.cli crea-utente $(UTENTE) --ruolo $(or $(RUOLO),analista)

telegram-login: ## Primo accesso dell'account Telegram (Fase 2)
	@echo "La sonda Telegram arriva con la Fase 2." && exit 1

eval: ## Valutazione sul set etichettato (Fase 3)
	@echo "La valutazione arriva con la Fase 3." && exit 1
