---
name: nuova-sonda
description: Crea o modifica una sonda di raccolta (Telegram, web, Tor, segnalazione manuale). Usare quando si aggiunge una fonte dati o si cambia il modo in cui una sonda legge e salva gli elementi.
argument-hint: "[nome-sonda] [tipo: telegram|web|tor|manuale]"
---

Crea la sonda indicata in: $ARGUMENTS

Se mancano nome o tipo, chiedili prima di scrivere codice.

## Contratto di una sonda

Una sonda fa una sola cosa: legge da una fonte e scrive elementi grezzi. Non estrae, non classifica, non valuta.

- Vive in `probes/<nome>/` con `probe.py`, `README.md` e i test in `tests/probes/test_<nome>.py`.
- Ha una riga nella tabella `sonda`: tipo, configurazione, cursore, stato, ultima esecuzione, ultimo errore.
- Espone `run(sonda_id)`: carica configurazione e cursore, raccoglie in modo incrementale, salva, aggiorna il cursore.
- Scrive solo in `elemento_grezzo` e `media`, attraverso le funzioni di `core/`. Mai file sparsi, mai CSV.
- Ogni elemento porta fonte, data di raccolta in UTC e `sha256`. Se l'hash esiste già, l'elemento si salta.
- Un errore non ferma le altre sonde: si registra in `ultimo_errore` e la sonda passa a `in_errore`.

## Passi

1. Leggi una sonda esistente in `probes/` e seguine la forma. Se è la prima, definisci la classe base in `probes/base.py`.
2. Scrivi la migrazione se servono campi nuovi di configurazione.
3. Implementa `run` con raccolta incrementale e rispetto dei limiti di frequenza della fonte: quando la fonte chiede di attendere, si attende.
4. Aggiungi un prefiltro prima di scaricare i file multimediali: parole chiave e presenza di link.
5. Crea le fixture in `tests/fixtures/<nome>/` e scrivi i test: raccolta di base, seconda esecuzione senza duplicati, ripresa dal cursore, gestione dell'errore.
6. Scrivi il `README.md` della sonda: cosa raccoglie, cosa non raccoglie, come si configura.
7. Esegui `make test` e `make lint`.
8. Passa i file modificati al subagente `revisore-conformita`.
9. Prova la sonda su dati reali con `make collect SONDA=<nome> LIMITE=<n>`, con un limite basso (un canale, poche decine di pagine). Verifica nel database che gli elementi siano arrivati con fonte, data e hash, e che una seconda esecuzione non crei duplicati.
10. Riporta all'utente quanti elementi sono stati raccolti e gli eventuali errori o blocchi incontrati.

## Regole per tipo

**telegram**
- Solo canali e gruppi pubblici, tramite Telethon.
- Non salvare mittenti, membri, profili: del messaggio restano testo, data, canale, link e media.
- La sonda è attiva per impostazione predefinita; `TELEGRAM_PROBE_ENABLED=false` la spegne senza toccare il codice.
- Il primo accesso dell'account lo fa l'utente con `make telegram-login`: serve il codice ricevuto sul telefono. Il file di sessione non va nel repository.
- Quando Telegram chiede di attendere, la sonda attende per il tempo indicato e non riprova prima.
- I nuovi canali scoperti da link e inoltri vanno in stato `da_approvare`: li attiva l'analista.

**web** e **tor**
- Scrapy con Playwright solo dove serve JavaScript.
- Per `.onion` lo stesso crawler usa il proxy SOCKS del contenitore Tor. Nessun browser Tor automatizzato.
- Ogni pagina diventa uno snapshot: HTML, schermata, traffico, hash, data.
- Captcha o blocco: l'URL va nella coda di revisione manuale. Non si aggira.
- Accesso passivo: nessun modulo compilato, nessun accesso.

**manuale**
- L'analista carica schermate, video o link. La sonda li salva come elementi grezzi con fonte `manuale` e l'identità di chi li ha caricati.

## Cosa non fare

- Non lanciare una raccolta reale senza limite, né fuori dal contenitore della sonda.
- Non fare richieste di rete nei test unitari: quelli usano solo le fixture.
- Non mettere credenziali nel codice o nelle fixture.
