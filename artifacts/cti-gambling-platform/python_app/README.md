# Betting

Prototipo di ricerca e analisi dei siti di scommesse illegali. Specifica in `docs/soluzione.md`, regole di progetto in `CLAUDE.md`, stato dei lavori in `docs/avanzamento.md`.

## Avvio

```bash
make setup            # ambiente Python locale per test e lint
make env              # crea .env con segreti casuali
make up               # database, archivio, portale, lavoratore, raccolta
make create-user UTENTE=nome RUOLO=amministratore
```

Il portale risponde su http://127.0.0.1:8000. Sezioni: cruscotto, siti (profilazione, Trust Index,
puntate, gemelli, legal entity, grafo, snapshot, report), revisione manuale, sonde, canali Telegram,
parole chiave, avvisi, ricerca nei contenuti, etichettatura, argomenti, emoji, valutazione, app Android,
registri pubblici, eventi sportivi, anomalie sui conti (dati sintetici), elenchi ADM, archivio, lavori, utenti.

Lo stato di ogni fase e le verifiche su dati reali ancora da fare sono in `docs/avanzamento.md`.

## Prove

```bash
docker compose up -d db
make test             # solo fixture, nessuna rete
make lint
make test-integration # dati reali: URL in PROVA_URLS, al massimo tre
```
