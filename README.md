# Betting

Prototipo di ricerca e analisi dei siti di scommesse illegali. Specifica in `docs/soluzione.md`, regole di progetto in `CLAUDE.md`, stato dei lavori in `docs/avanzamento.md`.

## Avvio

```bash
make setup            # ambiente Python locale per test e lint
make env              # crea .env con segreti casuali
make up               # database, archivio, portale, lavoratore, raccolta
make create-user UTENTE=nome RUOLO=amministratore
```

Il portale risponde su http://127.0.0.1:8000.

## Prove

```bash
docker compose up -d db
make test             # solo fixture, nessuna rete
make lint
make test-integration # dati reali: URL in PROVA_URLS, al massimo tre
```
