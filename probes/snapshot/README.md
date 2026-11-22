# Sonda `snapshot`

Fotografa **una sola pagina pubblica** per lavoro e la lascia nel secchio di arrivo.

## Cosa raccoglie

- HTML dopo il caricamento, schermata, traffico di rete (indirizzi e intestazioni, senza i corpi), catena dei reindirizzamenti.
- Per ogni file lo `sha256`; data di raccolta in UTC; nome e versione dello strumento; browser dichiarato.

## Cosa non fa

- Non compila moduli, non accede, non scarica file, non segue link.
- Non maschera il browser: niente modifiche al fingerprint, niente cambio di user agent, niente rotazione di proxy.
- Non risolve captcha. Una pagina di verifica, un 403/429/451 o un blocco geografico diventano uno snapshot `bloccato`, che il lavoratore interno porta in revisione manuale. Nessun nuovo tentativo automatico.
- Non contatta indirizzi interni: ogni richiesta verso un indirizzo non pubblico viene interrotta e contata.

## Come gira

Solo nel contenitore `raccolta`, su rete separata, con file system in sola lettura. Vede il database con il ruolo `raccolta` (due funzioni: `lavoro_prendi`, `lavoro_chiudi`) e l'archivio con una chiave che scrive solo nel secchio di arrivo. Gli hash sono ricalcolati sulla rete interna da `core/ingest.py`.

```
make collect SONDA=snapshot LIMITE=3      # al più tre pagine, poi si ferma
```

Come servizio (`docker compose up -d raccolta`) elabora gli URL inseriti dal portale, entro `RACCOLTA_MAX_PAGINE_ORA`.

Limiti per pagina: 45 s di caricamento, HTML fino a 5 MB, schermata fino a 6000 px di altezza.
