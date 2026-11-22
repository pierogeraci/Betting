# Stato del prototipo

Aggiornato al 22 novembre 2026. Tutte le funzioni della relazione tecnica sono costruite, nella
variante consentita dai vincoli di `CLAUDE.md`. Ogni modulo ha test su fixture (170 test, senza rete)
ed è passato da tre revisioni di conformità, con le correzioni applicate.

Ciò che **non** è stato verificato su dati reali è indicato per ogni fase: la sessione di sviluppo
non aveva accesso alla rete verso i siti, a Telegram, a Tor né ai modelli, e non aveva KVM.

## Fase 0 · Archivio, modello dati, elenchi ADM, inserimento manuale

| Fatto | Da fare su dati reali |
| --- | --- |
| Archivio per sha256, secchio di arrivo e di lavorazione, coda su tabella con ruolo `raccolta` ristretto | Verificare sul portale ADM gli indirizzi degli elenchi e inserirli in `config/fonti.yaml` |
| Elenchi ADM versionati, confronto con evidenza, `non_determinabile` senza elenco | `make test-integration` con tre URL in `PROVA_URLS` (criterio di uscita) |
| Snapshot di una pagina (HTML, schermata, traffico, icona, reindirizzamenti), blocchi in revisione manuale | |

## Fase 1 · Profilazione, Trust Index, portale, report

| Fatto | Da fare su dati reali |
| --- | --- |
| Sei collettori per area, pagine secondarie pubbliche (al più 6), dati di rete (DNS, RDAP, certificato verificato) | Profilare 50 siti reali |
| Trust Index fedele al foglio v0.5 (il test riproduce 11,5 · 6 · 8,75 → alto), copertura, regole ADM | Raccogliere 50 giudizi dell'analista (pagina Validazione) e misurare la concordanza: criterio di uscita |
| Puntate dai riquadri pubblici o da CSV; domini gemelli; giudizio; validazione; report | Tarare i pesi solo dopo la validazione, con una nuova versione delle regole |

## Fase 2 · Sonde

| Fatto | Da fare su dati reali |
| --- | --- |
| Telegram (Telethon): canali pubblici, nessun autore, sessione senza entità, attese rispettate | `make telegram-login` (lo fa l'utente), poi `make collect SONDA=telegram LIMITE=1` |
| Crawler web (Scrapy, robots.txt) e Tor (solo .onion, ogni richiesta del browser filtrata) | Configurare i semi dal portale; `make collect SONDA=web LIMITE=10` |
| Parole chiave, avvisi, canali da approvare, pianificatore, grafico della crescita | Due settimane di raccolta continua con `make up-raccolta`: criterio di uscita |

## Fase 3 · Estrazione e linguaggio

| Fatto | Da fare su dati reali |
| --- | --- |
| Contenitore di estrazione isolato: fotogrammi ai cambi di scena, hash percettivo, PP-OCRv5, QR, loghi, faster-whisper | `make modelli` (una volta, con rete), poi elaborare una ventina di pubblicità reali |
| Normalizzazione, entità, emoji per piattaforma, sentiment, riassunto, argomenti, estrazione con modello locale facoltativo | Confrontare due o tre modelli di trascrizione sull'italiano, come previsto dalla specifica |
| Classificatore senza dati Telegram, etichettatura, `make eval` | Etichettare qualche centinaio di elementi e misurare precisione e richiamo: criterio di uscita |

`make eval-gold` gira sugli esempi **sintetici** di `tests/gold/` e verifica solo che la pipeline funzioni.

## Fase 4 · App, legal entity, anomalie, eventi, social

| Modulo | Criterio | Stato |
| --- | --- | --- |
| App Android | Rapporto statico MobSF di un APK reale con domini nella lista URL | Codice e test con un rapporto d'esempio; da provare con `make up-app` |
| Analisi dinamica | Traffico di un'app osservato senza inviare dati | Codice pronto; richiede KVM (`make apk-dinamica`) |
| Legal entity | Candidati con evidenze, confermati dall'analista | Pronto; servono registri pubblici reali (pagina Registri) |
| Anomalie sui conti | Precisione e richiamo sulle anomalie inserite | Solo dati sintetici, per vincolo: le misure non dicono nulla su dati reali |
| Eventi sportivi | Rating con segnali spiegati | Pronto; servono serie di quote da un fornitore |
| Social (Facebook, VK, WeChat) | Ingresso manuale | Pronto (Nuovo elemento, con la piattaforma di origine) |

## Decisioni aperte per l'utente

- Base giuridica e destinatario dei dati (dalla specifica, ancora aperte).
- IBAN, portafogli e partite IVA dei siti: oggi l'IBAN entra nel grafo solo come paese, banca e impronta; portafogli e partite IVA per intero. Possono appartenere a prestanome.
- Riquadri "ultime puntate": le puntate strutturate non hanno nomi, ma HTML e schermate archiviate li contengono così come il sito li mostra (spesso mascherati).
- OCR e trascrizioni possono contenere nomi e voci: non c'è identificazione del parlante.
- `compose.sessione.yaml` usa la rete dell'host per il contenitore di raccolta: è una deroga al vincolo 7 valida solo nelle sessioni cloud.
