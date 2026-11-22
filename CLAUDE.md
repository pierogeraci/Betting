# Progetto Betting

Prototipo di un sistema di ricerca e analisi dei siti di scommesse illegali, a partire dal dossier Soft Strategy 2020 (capitolo 4). Uso previsto: antifrode, a supporto di concessionari e autorità.

La specifica completa è in `docs/soluzione.md`. Leggila prima di pianificare una fase. Le fonti sono la relazione tecnica Soft Strategy del 23 marzo 2021 e la matrice `Risk_matrix_gambling_online_v0.5.xlsx`: il prototipo copre tutte le funzioni della relazione, nella variante consentita dai vincoli qui sotto.

## Pipeline

```
sonde → archivio grezzo → estrazione → classificazione ed entità
      → profilazione del sito → Trust Index → console analista
```

Ogni modulo legge uno stadio e scrive il successivo. Nessun modulo ne chiama un altro direttamente: si passa dal database e dalla coda. Un URL inserito a mano deve poter percorrere tutta la valutazione senza alcuna sonda.

## Struttura

| Cartella | Contenuto |
| --- | --- |
| `core/` | Modelli, accesso al database, archivio dei file, coda |
| `probes/` | Sonde di raccolta, una per fonte |
| `extractors/` | OCR, trascrizione, normalizzazione del testo, analisi APK |
| `collectors/` | Collettori di profilazione del sito, uno per area |
| `scoring/` | Vulnerabilità, minaccia, Trust Index |
| `console/` | Portale web per l'analista (FastAPI, Jinja2, HTMX): tutto ciò che il sistema fa si usa da qui |
| `config/trust_index.yaml` | Pesi, soglie e matrice, con campo `version` |
| `tests/fixtures/` | Pagine, messaggi e file di esempio per i test |

## Stack

Python 3.12 · PostgreSQL con pgvector · archivio a oggetti compatibile S3 (SeaweedFS in locale) · coda sulla tabella `lavoro` (niente Celery né Redis) · SQLAlchemy, Alembic, psycopg · boto3 · tldextract · PyYAML · dnspython · FastAPI, Uvicorn, Jinja2, python-multipart, HTMX · Telethon · Scrapy con Playwright · Tor come proxy SOCKS · ffmpeg · PaddleOCR PP-OCRv5 · faster-whisper · Pillow, ImageHash · scikit-learn · sentence-transformers · Ollama per il modello linguistico locale · MobSF, mitmproxy, emulatore Android · pytest, httpx, ruff · Docker Compose.

Non aggiungere dipendenze fuori da questo elenco senza chiedere.

## Comandi

- `make setup`: ambiente Python locale (`.venv`) per test e lint
- `make env`: crea `.env` con segreti casuali, se non esiste
- `make up` / `make down`: avvia o ferma database, archivio, portale, lavoratore e raccolta
- `make init`: migrazioni, password del ruolo `raccolta`, secchi dell'archivio
- `make create-user UTENTE=<nome> RUOLO=analista|amministratore`: account del portale
- `make test`: test unitari, solo su fixture, senza rete; serve `docker compose up -d db`
- `make lint`: `ruff check` e `ruff format --check`
- `make collect SONDA=<nome> LIMITE=<n>`: esegue una sonda su dati reali nel suo contenitore, fermandosi al limite indicato. Sonde: `snapshot`, `adm`
- `make test-integration`: prove su dati reali; legge `PROVA_URLS` da `.env` (al massimo tre URL)
- `make telegram-login`: primo accesso dell'account Telegram; lo esegue l'utente (arriva con la Fase 2)
- `make eval`: valutazione sul set etichettato (arriva con la Fase 3)
- Nelle sessioni cloud dietro proxy: aggiungere `COMPOSE_EXTRA="-f compose.sessione.yaml"` ai comandi `make`

## Vincoli non negoziabili

1. Niente captcha solver, niente mascheramento del fingerprint, niente rotazione di proxy per aggirare i blocchi. Una pagina bloccata va nella coda di revisione manuale.
2. Sui siti analizzati non si creano account, non si compilano moduli, non si fanno depositi. Si osservano solo pagine pubbliche.
3. Telegram: la sonda è attiva e raccoglie dati reali. Solo canali e gruppi pubblici, con un account dedicato e rispettando i tempi di attesa imposti dal servizio. Nessun modello va addestrato o rifinito su dati Telegram.
4. Dati personali: non si archiviano autori dei messaggi, membri dei gruppi, profili. Si conserva solo ciò che identifica il sito pubblicizzato.
5. La profilazione degli scommettitori lavora solo su dati sintetici.
6. Sul dark web l'accesso è passivo: nessuna registrazione, nessun acquisto.
7. Crawler, Tor e analisi degli APK girano solo nei loro contenitori, su rete separata. Non eseguire mai dalla sessione codice scaricato o APK.
8. I segreti stanno in `.env`, mai nel repository.
9. Il sistema lavora su dati reali. Le raccolte si lanciano dalla sessione solo attraverso i contenitori (`make collect`), mai con script eseguiti direttamente sul sistema. Ogni prova reale ha un limite esplicito di canali, pagine o durata.

Se un compito richiede di violare uno di questi punti, fermati e chiedi.

## Convenzioni sui dati

- Elemento grezzo: fonte, data di raccolta in UTC, `sha256`. L'hash rende ogni passaggio ripetibile senza duplicati.
- Indicatore: `valore` tra `presente`, `assente`, `non_determinabile`; `evidenza` (URL, id dello snapshot, estratto); `certezza` da 0 a 1; nome e versione del collettore.
- "Non determinabile" non vale "assente": un dato che non si riesce a leggere non abbassa il rischio.
- Legalità: si decide per confronto con gli elenchi ADM (concessionari, siti inibiti) caricati in tabelle dedicate. Non si deduce dal testo del sito.
- Trust Index: segue la matrice del dossier v0.5. Vulnerabilità = somma dei pesi delle sette voci presenti; minaccia = tre variabili sulle puntate nelle 24 ore (puntata media, vincite totali, % vincite); indice = (vulnerabilità + minaccia) / 2. Pesi e soglie stanno solo in `config/trust_index.yaml`. Ogni punteggio registra la versione usata e la copertura. Senza dati di puntata la minaccia è non determinabile e non si emette alcun indice: si mostra la sola vulnerabilità.
- Confine di raccolta: i contenitori di raccolta vedono il database solo con il ruolo `raccolta` (funzioni `lavoro_prendi` e `lavoro_chiudi`) e scrivono solo nel secchio di arrivo. Un processo interno ricalcola gli hash e scrive le tabelle.
- Tabelle: `sonda`, `elemento_grezzo`, `media`, `estrazione`, `entita`, `sito`, `snapshot`, `indicatore`, `punteggio`, `revisione`; di servizio `lavoro`, `utente`, `adm_caricamento`, `adm_concessionario`, `adm_sito_inibito`.

## Fasi

| Fase | Contenuto | Criterio di uscita |
| --- | --- | --- |
| 0 | Archivio, modello dati, elenchi ADM, inserimento manuale dal portale | Un URL inserito a mano produce snapshot e confronto con ADM |
| 1 | Profilazione del sito, Trust Index secondo la matrice v0.5, portale analista, report per sito | 50 siti valutati e confrontati con il giudizio di un analista |
| 2 | Sonde: Telegram, web, Tor; parole chiave e avvisi | La lista URL cresce da sola per due settimane |
| 3 | OCR, trascrizione, classificatore, entità, sentiment, argomenti, emoji | Precisione e richiamo misurati sul set etichettato |
| 4 | App Android, legal entity, anomalie sui conti, rating eventi sportivi, social | Un criterio per ciascun modulo |

## Modo di lavorare

- Una fase per sessione. Prima il piano, poi il codice dopo l'approvazione.
- Ogni modulo nasce con i suoi test su fixture e si chiude con una prova su dati reali. Il criterio di uscita della fase diventa un test di integrazione.
- Skill del progetto: `/nuova-sonda`, `/nuovo-collettore`, `/regola-trust-index`, `/valuta`.
- Subagenti: `costruttore-collettore` per costruire collettori in parallelo, `revisore-conformita` dopo ogni modifica a sonde, collettori o crawler, `valutatore` per eseguire test e valutazione.
- Commenti, nomi di tabelle e messaggi per l'analista in italiano; nomi di funzioni e variabili in inglese.
