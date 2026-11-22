# Sonda `adm`

Scarica gli elenchi pubblici ADM (concessionari, siti inibiti) dagli indirizzi indicati in `config/fonti.yaml`.

- Un file per lavoro, solo `https`, al più 50 MB, senza autenticazione.
- Il file arriva nel secchio di arrivo; il lavoratore interno ne verifica l'hash, lo archivia come elemento grezzo e crea una nuova versione dell'elenco. Se il file è identico alla versione attiva si aggiorna solo la data di verifica.
- Formati letti: testo con un dominio per riga, CSV, tabella HTML. PDF e fogli di calcolo sono rifiutati con un messaggio: vanno esportati in CSV e caricati dal portale.

```
make collect SONDA=adm LIMITE=2           # uno scaricamento per elenco configurato
```

Gli indirizzi in `config/fonti.yaml` sono vuoti finché non vengono verificati sul portale ADM; nel frattempo gli elenchi si caricano dal portale, pagina "Elenchi ADM".
