---
name: valuta
description: Esegue la valutazione sul set etichettato e riporta precisione, richiamo e concordanza con l'analista. Da lanciare a mano prima di chiudere una fase o dopo una modifica a estrazione, classificazione o punteggio.
argument-hint: "[tutto | classificatore | estrazione | trust-index]"
disable-model-invocation: true
---

Ambito della valutazione: $ARGUMENTS (se vuoto: tutto)

Delega l'esecuzione al subagente `valutatore`, poi presenta il risultato all'utente.

## Cosa si misura

| Ambito | Dati | Misure |
| --- | --- | --- |
| classificatore | `tests/gold/messaggi.jsonl` | Precisione e richiamo su "pubblicità di gioco sì o no" |
| estrazione | `tests/gold/entita.jsonl` | Precisione e richiamo per tipo di entità: URL, dominio, marchio, portafoglio, codice |
| trust-index | `tests/gold/siti.jsonl` | Concordanza tra classe automatica e giudizio dell'analista; matrice di confusione |

## Passi

1. Esegui `make eval` con l'ambito richiesto.
2. Confronta con l'ultima riga di `docs/valutazioni.md`.
3. Presenta una tabella: misura, valore precedente, valore attuale, differenza.
4. Elenca fino a dieci errori, i più istruttivi, con l'elemento e l'evidenza.
5. Aggiungi una riga a `docs/valutazioni.md`: data, commit, versione delle regole, misure.

## Regole

- Non modificare i file in `tests/gold/`: li cura l'analista.
- Non correggere il codice in questa skill: riporta e basta.
- Se il set etichettato ha meno di 100 elementi per un ambito, dillo: i numeri non sono ancora affidabili.
- Un peggioramento si riporta in cima, non in fondo.
