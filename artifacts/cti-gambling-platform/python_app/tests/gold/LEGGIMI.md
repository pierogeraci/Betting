# Set di esempi del repository

`esempi.jsonl` contiene esempi **sintetici**, scritti per il progetto: nessun dato raccolto
e nessun dato Telegram. Servono a verificare che la pipeline di valutazione funzioni
(`make eval-gold`), non a misurare il sistema reale.

Le misure che contano si fanno sul set etichettato dall'analista nel portale
(pagina Etichettatura), con `make eval`. Il subagente `valutatore` non modifica questa cartella.
