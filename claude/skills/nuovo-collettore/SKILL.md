---
name: nuovo-collettore
description: Crea o modifica un collettore di profilazione del sito (infrastruttura, domini gemelli, titolo a operare, dati aziendali, pagamenti, identificazione, offerta). Usare quando si aggiunge un indicatore rilevato su un sito di scommesse.
argument-hint: "[nome-collettore] [area]"
---

Crea il collettore indicato in: $ARGUMENTS

Se mancano nome o area, chiedili prima di scrivere codice.

## Contratto di un collettore

Un collettore riceve uno snapshot di un sito e restituisce indicatori. Non decide il rischio: quello è compito di `scoring/`.

- Vive in `collectors/<nome>.py`, con test in `tests/collectors/test_<nome>.py`.
- Espone `collect(snapshot) -> list[Indicatore]` ed è una funzione pura sullo snapshot: stessi dati, stesso risultato.
- Dichiara `NOME` e `VERSIONE`. La versione cresce a ogni cambio di logica.
- Lavora sullo snapshot già salvato. Se gli servono dati esterni (DNS, registrazione del dominio, certificati), li chiede alle funzioni di `core/` che li salvano come elementi grezzi.

## Forma di un indicatore

```python
Indicatore(
    codice="pagamento_criptovalute",
    valore="presente",            # presente | assente | non_determinabile
    evidenza=Evidenza(url=..., snapshot_id=..., estratto="..."),
    certezza=0.9,                 # da 0 a 1
    collettore=NOME,
    versione=VERSIONE,
)
```

Regole sul valore:

- `presente` solo con un'evidenza che un analista può aprire e controllare.
- `assente` solo se la pagina che conterrebbe il dato è stata letta e il dato non c'è.
- `non_determinabile` in tutti gli altri casi: pagina non raggiunta, contenuto dietro accesso, testo ambiguo.

Non trasformare mai un "non l'ho trovato" in `assente`.

## Aree e indicatori di partenza

| Area | Indicatori |
| --- | --- |
| Infrastruttura | DNS, registrazione del dominio, certificato TLS, rete e hosting, tecnologie |
| Domini gemelli | Stesso certificato, stessa icona, stessi identificativi di tracciamento |
| Titolo a operare | Dominio negli elenchi ADM, numero di concessione dichiarato, logo ADM, licenze estere dichiarate |
| Dati aziendali | Ragione sociale, sede, partita IVA |
| Pagamenti | Carte, bonifico UE, fornitori terzi, criptovalute, conto offshore |
| Identificazione | Registrazione richiesta, documento richiesto, più account per conto |
| Offerta | Tipi di gioco, mercati e quote visibili |

Le sette vulnerabilità del dossier hanno questi codici: `piu_account_per_conto`, `pagamento_conto_ue`, `assenza_registrazione`, `assenza_documento`, `pagamento_terze_parti`, `pagamento_criptovalute`, `pagamento_offshore`.

## Passi

1. Leggi un collettore esistente e seguine la forma.
2. Aggiungi in `tests/fixtures/snapshots/` almeno tre snapshot: uno con l'indicatore presente, uno assente, uno non determinabile.
3. Scrivi prima i test sui tre casi, poi il collettore.
4. Preferisci regole esplicite (selettori, espressioni regolari, elenchi di termini multilingue). Usa un modello linguistico solo per testo libero come le condizioni d'uso, e salva sempre l'estratto che giustifica la risposta.
5. Registra il collettore nell'elenco di `collectors/__init__.py`.
6. Se l'indicatore entra nel punteggio, non toccare i pesi qui: usa `/regola-trust-index`.
7. Esegui `make test` e `make lint`.
8. Prova il collettore su almeno cinque snapshot reali presi dall'archivio e riporta, per ciascuno, valore ed evidenza. Se l'archivio è vuoto, raccogli prima qualche sito con `make collect`.

## Cosa non fare

- Non creare account, non compilare moduli, non simulare depositi.
- Non dedurre la legalità dal testo del sito: il confronto è con le tabelle degli elenchi ADM.
- Non fare richieste di rete nei test unitari.
