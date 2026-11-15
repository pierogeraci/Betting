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

- Vulnerabilità V e minaccia T sono medie pesate sui soli indicatori determinati: `presente` vale 1, `assente` vale 0, `non_determinabile` è escluso da numeratore e denominatore.
- Copertura C = indicatori determinati / indicatori totali. Si calcola separatamente per V e per T.
- V e T si dividono in livelli secondo le soglie; la matrice livello V × livello T restituisce la classe di rischio, cioè il Trust Index.

Regole che precedono il calcolo, in questo ordine:

1. Dominio di un concessionario ADM: nessuna valutazione di illegalità.
2. Logo o numero di concessione ADM esposti da un dominio che non è nell'elenco: segnalazione immediata, a prescindere dal punteggio.
3. Copertura sotto soglia: nessun indice, il sito va alla revisione dell'analista.

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
- Le tre variabili della minaccia sono una proposta in attesa della matrice originale: esposizione verso l'Italia, opacità dell'operatore, portata promozionale. Se l'utente fornisce quelle originali, sostituiscile e annotalo nel changelog.
- Non cambiare i pesi per far passare un test o per migliorare la concordanza su pochi casi: segnala il disaccordo e lascia decidere l'utente.
