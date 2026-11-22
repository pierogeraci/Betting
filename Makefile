# Comandi del progetto. `make help` li elenca.
SHELL := /bin/bash
PY := .venv/bin/python
# COMPOSE_EXTRA=-f compose.sessione.yaml nelle sessioni cloud dietro proxy.
COMPOSE := BUILDX_BAKE_ENTITLEMENTS_FS=0 docker compose -f compose.yaml $(COMPOSE_EXTRA)
LIMITE ?=
SONDA ?=

.PHONY: help setup env up up-raccolta up-app apk-dinamica modelli anomalie down init test lint collect test-integration create-user telegram-login eval

help:
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*## "}{printf "  %-18s %s\n", $$1, $$2}'

setup: ## Ambiente Python locale per test e lint
	python3.12 -m venv .venv && .venv/bin/pip install -q -U pip && .venv/bin/pip install -q -e '.[dev]'

env: ## Crea .env con segreti casuali, se non esiste
	@test -f .env && echo ".env esiste già" || $(PY) -m core.envfile

up: ## Avvia database, archivio, portale e lavoratore (nessuna raccolta)
	$(COMPOSE) up -d --build db archivio init portale lavoratore

up-raccolta: ## Solo in esercizio: avvia i contenitori di raccolta continua (snapshot, Telegram, Tor)
	@echo "Avvio delle raccolte continue su dati reali, con i tetti configurati in .env e nelle sonde."
	$(COMPOSE) --profile raccolta up -d --build raccolta telegram tor estrazione

down: ## Ferma tutto (i dati restano nei volumi)
	$(COMPOSE) down

init: ## Migrazioni, ruolo di raccolta, secchi dell'archivio
	$(COMPOSE) run --rm init

test: ## Test unitari: solo fixture, nessuna rete. Serve `docker compose up -d db`
	$(PY) -m pytest

lint: ## Formattazione e controlli statici
	$(PY) -m ruff check . && $(PY) -m ruff format --check .

collect: ## Prova su dati reali nel contenitore della sonda, con tetto: make collect SONDA=snapshot|adm|rete|telegram|web|tor LIMITE=<n>
	@test -n "$(SONDA)" || { echo "Indica la sonda: SONDA=snapshot|adm|rete|telegram|web|tor"; exit 1; }
	@[[ "$(LIMITE)" =~ ^[1-9][0-9]*$$ ]] || { echo "Indica un limite esplicito: LIMITE=<n> (lavori per snapshot e adm, canali per telegram, pagine per web e tor)"; exit 1; }
ifneq ($(filter $(SONDA),telegram web tor),)
	$(COMPOSE) run --rm init python -m core.cli accoda-sonda $(SONDA) --limite $(LIMITE)
	$(COMPOSE) --profile raccolta run --rm $(if $(filter telegram,$(SONDA)),telegram,raccolta) python -m probes.runner --sonda $(SONDA) --limite 1 --tetto $(LIMITE)
else
	$(COMPOSE) run --rm init python -m core.cli accoda-sonda $(SONDA)
	$(COMPOSE) --profile raccolta run --rm raccolta python -m probes.runner --sonda $(SONDA) --limite $(LIMITE)
endif

test-integration: ## Prova su dati reali: URL in PROVA_URLS (al massimo tre) → snapshot → confronto ADM
	$(COMPOSE) up -d --build db archivio lavoratore
	$(COMPOSE) run --rm init python -m tests.integration.prepara
	$(COMPOSE) --profile raccolta run --rm raccolta python -m probes.runner --sonda snapshot --limite 3
	$(COMPOSE) run --rm init python -m pytest -m integration tests/integration -q

up-app: ## Avvia l'analisi statica degli APK (MobSF su rete interna senza Internet)
	$(COMPOSE) --profile app up -d --build mobsf apk

apk-dinamica: ## Una analisi dinamica di APK in coda: emulatore usa e getta + mitmproxy (serve KVM)
	-$(COMPOSE) --profile apk-dinamica rm -sfv emulatore mitm
	-docker volume rm -f betting_flussi_mitm
	$(COMPOSE) --profile apk-dinamica up -d emulatore mitm
	-$(COMPOSE) --profile apk-dinamica run --rm apk-dinamica
	$(COMPOSE) --profile apk-dinamica rm -sfv emulatore mitm
	-docker volume rm -f betting_flussi_mitm

modelli: ## Scarica una volta i modelli di OCR e trascrizione nel volume `modelli` (serve la rete)
	$(COMPOSE) --profile raccolta run --rm --no-deps -v betting_modelli:/modelli -e HF_HUB_OFFLINE=0 --entrypoint python estrazione -c "from extractors.media import ocr_engine; ocr_engine(); import os; from faster_whisper import WhisperModel; WhisperModel(os.environ.get('MODELLO_TRASCRIZIONE', 'large-v3'))"

anomalie: ## Anomalie sui conti, solo dati sintetici, da terminale
	$(PY) -c "from scoring.anomalies import run; import json; print(json.dumps(run()['valutazione'], indent=1))"

create-user: ## Crea un account del portale: make create-user UTENTE=nome RUOLO=amministratore
	@test -n "$(UTENTE)" || { echo "Indica UTENTE=<nome>"; exit 1; }
	$(COMPOSE) run --rm init python -m core.cli crea-utente $(UTENTE) --ruolo $(or $(RUOLO),analista)

telegram-login: ## Primo accesso dell'account Telegram dedicato: lo esegue l'utente (serve il codice sul telefono)
	$(COMPOSE) --profile raccolta run --rm -it telegram python -m probes.telegram.login

eval: ## Valutazione sul set etichettato: entità e classificatore (AMBITO=entita|classificatore|gold)
	$(COMPOSE) run --rm init python -m core.evaluation $(if $(AMBITO),--ambito $(AMBITO),)

eval-gold: ## Valutazione locale sul set di esempi del repository, senza database
	$(PY) -m core.evaluation --ambito gold
