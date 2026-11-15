# Progetto Betting

Prototipo di un sistema di ricerca e analisi dei siti di scommesse illegali, a partire dal dossier Soft Strategy 2020 (capitolo 4). Uso previsto: antifrode, a supporto di concessionari e autorità.

La specifica completa è in `docs/soluzione.md`. Leggila prima di pianificare una fase.

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
| `console/` | Applicazione web per l'analista |
| `config/trust_index.yaml` | Pesi, soglie e matrice, con campo `version` |
| `tests/fixtures/` | Pagine, messaggi e file di esempio per i test |

## Stack

Python 3.12 · PostgreSQL · archivio a oggetti compatibile S3 · Celery con Redis (nella Fase 0 basta una tabella di lavori) · Telethon · Scrapy con Playwright · Tor come proxy SOCKS · ffmpeg · PaddleOCR PP-OCRv5 · faster-whisper · MobSF · Docker Compose.

Non aggiungere dipendenze fuori da questo elenco senza chiedere.

## Comandi

La Fase 0 deve creare questi comandi; quando esistono, aggiorna questa sezione con la forma esatta.

- `make test`: test unitari, solo su fixture, senza rete
- `make collect SONDA=<nome> LIMITE=<n>`: esegue una sonda su dati reali nel suo contenitore, fermandosi al limite indicato
- `make test-integration`: prove su dati reali, dalla raccolta al Trust Index
- `make telegram-login`: primo accesso dell'account Telegram; lo esegue l'utente, perché richiede il codice ricevuto sul telefono
- `make lint`: formattazione e controlli statici
- `make eval`: valutazione sul set etichettato
- `docker compose up -d db`: database locale

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
- Trust Index: pesi e soglie stanno solo in `config/trust_index.yaml`. Ogni punteggio registra la versione usata e la copertura. Sotto la soglia di copertura non si emette alcun indice.
- Tabelle: `sonda`, `elemento_grezzo`, `media`, `estrazione`, `entita`, `sito`, `snapshot`, `indicatore`, `punteggio`, `revisione`.

## Fasi

| Fase | Contenuto | Criterio di uscita |
| --- | --- | --- |
| 0 | Archivio, modello dati, elenchi ADM, inserimento manuale | Un URL inserito a mano produce snapshot e confronto con ADM |
| 1 | Profilazione del sito, Trust Index, console analista | 50 siti valutati e confrontati con il giudizio di un analista |
| 2 | Sonde: Telegram, web, Tor | La lista URL cresce da sola per due settimane |
| 3 | OCR, trascrizione, classificatore, estrazione delle entità | Precisione e richiamo misurati sul set etichettato |
| 4 | App Android, legal entity, anomalie sui conti, social | Un criterio per ciascun modulo |

## Modo di lavorare

- Una fase per sessione. Prima il piano, poi il codice dopo l'approvazione.
- Ogni modulo nasce con i suoi test su fixture e si chiude con una prova su dati reali. Il criterio di uscita della fase diventa un test di integrazione.
- Skill del progetto: `/nuova-sonda`, `/nuovo-collettore`, `/regola-trust-index`, `/valuta`.
- Subagenti: `costruttore-collettore` per costruire collettori in parallelo, `revisore-conformita` dopo ogni modifica a sonde, collettori o crawler, `valutatore` per eseguire test e valutazione.
- Commenti, nomi di tabelle e messaggi per l'analista in italiano; nomi di funzioni e variabili in inglese.
