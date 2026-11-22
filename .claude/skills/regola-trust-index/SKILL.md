---
name: regola-trust-index
description: Aggiunge o modifica pesi, soglie, livelli o regole del Trust Index. Usare per ogni cambiamento al calcolo di vulnerabilità, minaccia o classe di rischio.
argument-hint: "[descrizione della modifica]"
---

Modifica richiesta: $ARGUMENTS

## Dove vive il calcolo

- `config/trust_index.yaml`: unica fonte di pesi, soglie, livelli e matrice. Ha un campo `version`.
- `scoring/`: codice che legge il file e calcola. Non contiene numeri scritti a mano.

## Come si calcola

Il calcolo segue la matrice del dossier, foglio v0.5 (`docs/soluzione.md`, sezione Calcolo).

- Vulnerabilità V = somma dei pesi delle sette voci `presente`. Le voci `non_determinabile` non contano, ma si mostra anche il massimo possibile (come se fossero presenti). Livelli: basso sotto 6, medio sotto 12, alto oltre.
- Copertura = voci determinate / voci totali. Sotto `copertura_minima`, se il livello minimo e il massimo non coincidono, il livello non si emette.
- Minaccia M dalle puntate nelle 24 ore: tre variabili (puntata media arrotondata per eccesso, somma delle vincite, % vincite) con voto 1-3; M = media dei voti arrotondata per eccesso × 3. Senza puntate sufficienti M non è determinabile.
- Trust Index = (V + M) / 2. Livelli: basso sotto 4, medio fino a 7, alto oltre.

Regole che precedono il calcolo, in questo ordine:

1. Dominio di un concessionario ADM: nessuna valutazione di illegalità.
2. Logo o numero di concessione ADM esposti da un dominio che non è nell'elenco: segnalazione immediata, a prescindere dal punteggio.
3. Copertura sotto soglia o minaccia non determinabile: nessun indice; con copertura bassa il sito va alla revisione dell'analista.

## Passi

1. Leggi `config/trust_index.yaml` e descrivi all'utente l'effetto atteso della modifica prima di applicarla.
2. Applica la modifica e incrementa `version`. Aggiungi una riga in `config/CHANGELOG.md`: versione, data, cosa cambia, perché.
3. Se nasce un indicatore nuovo, verifica che esista un collettore che lo produce. Se manca, fermati e proponi `/nuovo-collettore`.
4. Aggiorna i test di `tests/scoring/`: almeno un caso per ogni regola toccata, più i casi limite sulle soglie.
5. Ricalcola il campione validato con la versione vecchia e con la nuova. Riporta quanti siti cambiano classe e quali.
6. Riporta la concordanza con i giudizi dell'analista prima e dopo.
7. Esegui `make test`.

## Vincoli

- Ogni punteggio salvato registra la versione delle regole, la copertura e gli indicatori usati con le loro evidenze. Un punteggio deve potersi ricostruire.
- Non ricalcolare né sovrascrivere i punteggi storici: si aggiunge un punteggio nuovo con la versione nuova.
- Le tre variabili della minaccia sono quelle della matrice originale v0.5. Esposizione verso l'Italia, opacità e portata promozionale restano informazioni di contesto, fuori dall'indice.
- Non cambiare i pesi per far passare un test o per migliorare la concordanza su pochi casi: segnala il disaccordo e lascia decidere l'utente.
