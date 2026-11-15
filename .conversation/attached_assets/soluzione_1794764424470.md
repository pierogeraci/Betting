# Progetto Betting – Soluzione per i prototipi

Nov 15, 2026 · @Piero Geraci

## Sintesi

La soluzione robusta è una sola piattaforma a pipeline, non dieci scraper separati: sonde di raccolta, archivio grezzo, estrazione (testo, OCR, audio), classificazione, profilazione del sito, Trust Index, revisione dell'analista.

Tre scelte la rendono più solida dei prototipi del 2020:

- **Legalità per confronto con gli elenchi ADM, non per interpretazione del sito.** Dal 13 novembre 2025 le concessioni sono 52, assegnate a 46 operatori, con un solo sito per concessione ([fonte](https://www.corrieredellosport.it/scommesse/nuovi-siti-scommesse), [fonte](https://www.casinos.com/it/news/adm-stretta-skin-13-novembre-un-sito-operatore)). ADM pubblica anche l'elenco dei domini inibiti, 12.448 a luglio 2026 ([fonte](https://tg24.sky.it/cronaca/2026/07/27/andrea-pirlo-fonbet-sito-scommesse)). Il controllo "autorizzato o no" diventa una ricerca in elenco.
- **Fonti ufficiali o accessibili al posto dell'aggiramento anti-scraping.** I prototipi Facebook e WeChat sono falliti proprio su quel punto. Captcha solver e mascheramento del fingerprint sono la parte meno stabile e più esposta legalmente: restano fuori dal disegno.
- **Modelli pre-addestrati al posto di modelli costruiti in casa.** Whisper per l'audio, PP-OCRv5 per il testo nei video e un modello linguistico multilingue per entità ed emoji sostituiscono ULMFiT/ELMo, VidScraper e la trascrizione manuale.

Ordine di costruzione: prima il nucleo (lista URL, profilazione del sito, Trust Index), che produce valore da solo. Poi le sonde, poi il multimediale, per ultimi Android, legal entity e profilazione utenti.

Due decisioni sono già prese: il prototipo lavora su dati reali fin dall'inizio e la sonda Telegram è attiva. I termini di Telegram dal 2026 vietano la raccolta di dati per usi di intelligenza artificiale: resta un rischio noto e accettato. La profilazione dei giocatori richiede dati che possiede solo un concessionario o un'autorità.

Ipotesi di lavoro: prototipi dimostrativi e non di produzione, team piccolo, stack Python come nel dossier, uso antifrode a favore di concessionari e autorità.

## I prototipi del dossier

Il dossier descrive quattordici prototipi o filoni; nel 2020 solo le sonde Telegram e la matrice su foglio di calcolo erano dichiarate completate.

| Prototipo | Stato dichiarato nel 2020 | Punto debole | Cosa propongo |
| --- | --- | --- | --- |
| Sonde Telegram su canali e gruppi pubblici | Primo prototipo completato, anche per audio e video | Dipende dai termini d'uso di Telegram, cambiati nel 2026 | Riscrittura su client ufficiale con gestione sonde in database |
| Scraper HTML (scrapy, pyspider, proxy, captcha solver) | Funzionante; output su file di testo, controllo manuale | pyspider è archiviato da giugno 2024 ([fonte](https://github.com/binux/pyspider)); il resto è una rincorsa alle protezioni | Scrapy con browser reale, senza solver |
| Ambiente Tor (VPN, Tor Browser, Selenium, Geckodriver) | Implementato | Catena di quattro componenti, fragile | Stesso crawler web instradato su proxy Tor |
| Facebook (Selenium, CSV) | Solo gruppi aperti, pochi risultati | Meta ha chiuso lo scraping senza login nel 2025 ([fonte](https://www.datashake.com/blog/facebook-social-data-api-in-2026)) | Connettore su canali ufficiali, tramite partner |
| WeChat (bot, client web) | Risultati deludenti | La piattaforma limita i bot | Fuori dal primo ciclo; solo segnalazioni manuali |
| VK | Citato tra le fonti, nessun prototipo | Non descritto | Da valutare dopo le altre sonde |
| Video (VidScraper) | Risultati sotto le attese | La libreria recupera metadati, non legge il contenuto | Fotogrammi con ffmpeg e OCR |
| Audio | Processo manuale dell'operatore | Suddivisione a mano; FFmpeg estrae l'audio ma non lo trascrive | Trascrizione automatica in locale |
| NLP, sentiment, emoji (ULMFiT, ELMo) | Prototipo su parola chiave | Modelli superati, da addestrare su molto testo | Modello multilingue pre-addestrato ed estrazione strutturata |
| Profilazione del sito | Metodologia definita | Estrazione non automatizzata | Collettori per dominio con evidenze |
| Matrice Trust Index (4 fogli) | Sviluppata, non integrata nel sistema | Pesi non validati, calcolo su foglio | Motore di regole versionato nel database |
| Associazione a legal entity | Non risolta | Nessuna metodologia | Grafo di entità e registri pubblici; l'analista conferma |
| Profilazione scommettitori | Metodologie studiate | I dati necessari non sono visibili dall'esterno | Modulo di anomalie sui dati dell'operatore |
| App Android (ApkAnalyzer, BlueStacks) | Procedura manuale | Nessuna automazione | Analisi statica e dinamica automatizzata |

La causa comune della fragilità è strutturale. Ogni prototipo scrive in un formato suo (testo, CSV, JSON, foglio) e nessuno alimenta il successivo senza un passaggio manuale. Le fonti più difficili sono state affrontate aggirando le protezioni, cioè sul terreno dove la piattaforma vince sempre.

Una precisazione sul testo: dove il dossier scrive "text to speech" intende la trascrizione, cioè speech to text.

## Architettura proposta

Cinque tipi di fonte scrivono in un unico archivio grezzo; da lì ogni passaggio legge uno stadio e scrive il successivo.

&#91;embedded content: architettura · 5 fonti, 4 estrattori, 1 indice\]

Le sonde scrivono solo nell'archivio grezzo. Gli elenchi ADM entrano nella profilazione e l'analista convalida il Trust Index.

- Ogni elemento ha un hash: si può rielaborare senza raccoglierlo di nuovo, ad esempio quando migliora l'OCR.
- Le code separano i moduli: una sonda che cade non ferma estrazione e valutazione.
- Le correzioni dell'analista tornano nel sistema come esempi etichettati e come tarature dei pesi.
- Aggiungere una fonte significa scrivere una sonda, non toccare il resto.
- Tutto parte anche da un URL inserito a mano: il nucleo di valutazione non dipende dalle sonde.

## Soluzione per ciascun prototipo

Ogni modulo legge e scrive solo nell'archivio comune: si può costruire, provare e sostituire da solo.

### Sonde Telegram

- Client MTProto ufficiale tramite la libreria Telethon, con account dedicati e solo su canali e gruppi pubblici. La sonda è attiva da subito e raccoglie dati reali.
- Una sonda è una riga in database: account, elenco canali, cursore dell'ultimo messaggio letto, stato, ultimo errore. È la "gestione delle sonde" che il dossier chiede.
- Raccolta incrementale con rispetto dei limiti di frequenza imposti dal servizio. I file multimediali si scaricano solo se il messaggio supera un prefiltro su parole chiave e link.
- Scoperta di nuovi canali dai link, inoltri e menzioni trovati nei messaggi già raccolti; l'analista approva ogni nuovo canale.
- Criterio di uscita: due settimane di raccolta continua senza intervento e senza duplicati.

### Crawler web e Tor

- Scrapy come motore (code, tentativi, deduplica, limitazione di velocità) con Playwright per le pagine che richiedono JavaScript.
- Per i siti .onion lo stesso crawler passa da un proxy SOCKS verso un demone Tor in un contenitore isolato. Niente Tor Browser pilotato da Selenium.
- Ogni pagina diventa uno snapshot: HTML, schermata, traffico di rete, hash e data. È la prova che l'analista e un'autorità possono riesaminare.
- Semi iniziali: lista URL dalle pubblicità, directory del dark web citate nel dossier, elenco ADM dei siti inibiti per trovare i domini gemelli.
- Pagine con captcha o blocchi vanno in una coda di revisione manuale. Non progetto solver né mascheramento del fingerprint.

### Social: Facebook, VK, WeChat

- Facebook e Instagram: l'unico accesso su larga scala ai contenuti pubblici è la Meta Content Library, riservata a ricercatori accademici e non profit approvati ([fonte](https://transparency.meta.com/researchtools/meta-content-library)). La strada è un partner universitario, non uno scraper.
- VK: da valutare l'API ufficiale dopo le altre sonde; il dossier non descrive alcun prototipo.
- WeChat: nessun accesso automatico stabile. Resta fuori dal primo ciclo.
- Per tutte le fonti chiuse serve un ingresso manuale: l'analista carica schermate, video o link e questi seguono la stessa pipeline delle sonde.

### Video e immagini

- ffmpeg campiona i fotogrammi ai cambi di scena; un hash percettivo elimina i quasi duplicati.
- OCR con PP-OCRv5 di PaddleOCR, nato per il testo "in scena" e disponibile per 106 lingue ([fonte](https://www.paddleocr.ai/v3.5.0/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html)). Copre i problemi elencati nel dossier: bassa risoluzione, sfondi irregolari, testo colorato.
- Lettura dei codici QR, che spesso contengono direttamente l'URL del sito.
- Riconoscimento dei loghi per somiglianza con una raccolta di marchi noti, compreso il logo ADM usato senza titolo.
- Ogni testo estratto conserva il tempo del fotogramma, così la ricerca per tag nel tempo descritta nel dossier resta possibile.

### Audio

- ffmpeg estrae la traccia; un rilevatore di voce scarta musica e silenzi.
- Trascrizione in locale con faster-whisper e il modello Whisper large-v3, che copre 99 lingue ([fonte](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks)). I dati non escono verso servizi cloud.
- Nel 2026 esistono modelli aperti più accurati sull'inglese ([fonte](https://pinggy.io/blog/best_open_source_self_hosted_speech_to_text_models/)). La scelta finale va fatta provando due o tre modelli su una ventina di pubblicità reali in italiano.

### Linguaggio, entità, emoji

- Normalizzazione prima di tutto: forme Unicode, caratteri sosia, separatori inseriti per offuscare, emoji convertite nel loro nome.
- Estrazione deterministica con espressioni regolari per ciò che ha una forma fissa: URL, domini, nomi utente, indirizzi di portafogli crypto, codici promozionali, numeri di concessione.
- Classificatore "pubblicità di gioco sì o no": vettori di un modello multilingue pre-addestrato più un classificatore leggero, addestrato su poche centinaia di esempi etichettati.
- Estrazione strutturata con un modello linguistico eseguito in locale, su schema fisso: marchio, URL, giochi, metodi di pagamento, bonus, lingua, riferimenti all'Italia.
- Un set di esempi etichettati a mano misura precisione e richiamo a ogni modifica. Senza questo set non si può dire se il prototipo migliora.

### Profilazione del sito

Per ogni dominio un insieme di collettori indipendenti produce indicatori. Ogni indicatore porta valore, evidenza (URL, snapshot, estratto) e grado di certezza.

| Area | Cosa si raccoglie |
| --- | --- |
| Infrastruttura | DNS, dati di registrazione del dominio, certificati TLS, rete e hosting, tecnologie usate |
| Domini gemelli | Stesso certificato, stessa icona, stessi identificativi di tracciamento |
| Titolo a operare | Presenza negli elenchi ADM, numero di concessione dichiarato, licenze estere dichiarate |
| Dati aziendali | Ragione sociale, sede, partita IVA da piè di pagina e condizioni |
| Pagamenti | Carte, bonifico UE, fornitori terzi, criptovalute, conti offshore |
| Identificazione | Registrazione richiesta o no, documento richiesto o no, più account per conto |
| Offerta | Tipi di gioco, mercati e quote visibili |

Le licenze estere si confrontano con i registri pubblici dei regolatori. Quello di Curaçao, ad esempio, pubblica licenze e provvedimenti ([fonte](https://www.gamingcontrolcuracao.org/en/133i348441001)).

Il collettore osserva pagine pubbliche e moduli senza compilarli: non crea account e non effettua depositi.

### Associazione a una legal entity

- Il dossier la dà per non risolta, e in automatico non lo sarà. L'obiettivo realistico è proporre candidati ordinati per punteggio.
- Grafo di entità: dominio, indirizzo IP, certificato, identificativi di tracciamento, portafogli, ragione sociale, licenza, fornitore di pagamento.
- Confronto dei nomi estratti con registri societari pubblici e con i registri delle licenze.
- Il raggruppamento dei domini gemelli è il risultato più utile: una rete di siti si tratta come un solo operatore.

### Profilazione degli scommettitori

- Stato dei conti, ricariche, vincite rispetto alle puntate: questi dati esistono solo nei sistemi dell'operatore. Dall'esterno si otterrebbero solo entrando in conti altrui, e questo non va progettato.
- Il prototipo sensato è un modulo di rilevazione anomalie su uno schema "conto di gioco", provato su dati sintetici.
- Gli indicatori del dossier diventano le variabili: importi erogati rispetto ai puntati, concentrazione di vincite, frequenza delle ricariche, strumenti e valute usati, conti sospesi.
- Regole esplicite più un modello di anomalia; ogni segnalazione indica quale indicatore l'ha generata.
- Destinatari: un concessionario sui propri dati, o un'autorità su dati acquisiti in indagine.

### App Android

- Analisi statica con MobSF, open source, con API e immagine Docker ([fonte](https://appsecsanta.com/mobsf)). Produce in JSON permessi, librerie pubblicitarie, URL e domini nel codice, certificato di firma.
- Analisi dinamica nell'emulatore Android ufficiale al posto di BlueStacks, con un proxy di intercettazione per il traffico verso i servizi pubblicitari.
- I domini trovati entrano nella lista URL e seguono la profilazione del sito.
- Gli APK si eseguono solo in un ambiente isolato e usa e getta.

## Matrice di rischio e Trust Index

I quattro fogli del dossier diventano quattro stadi nel database, ognuno ricalcolabile dal precedente: dato grezzo, indicatore raffinato, punteggi di vulnerabilità e minaccia, Trust Index.

### Vulnerabilità

Le sette vulnerabilità del dossier diventano indicatori a tre valori: presente, assente, non determinabile. Il terzo valore è essenziale: un sito che non lascia vedere la cassa non è un sito sicuro.

| Vulnerabilità (dal dossier) | Dove la sonda la rileva |
| --- | --- |
| Più account collegati a un unico conto | Condizioni d'uso, pagine di aiuto |
| Pagamento da conto corrente UE | Pagina cassa, domande frequenti |
| Assenza di registrazione | Percorso di gioco osservato senza accesso |
| Nessun documento richiesto all'iscrizione | Modulo di registrazione, condizioni |
| Pagamento tramite fornitori terzi | Pagina cassa, script e domini caricati |
| Pagamento e puntata in criptovalute | Pagina cassa, indirizzi di portafoglio nel testo |
| Pagamento su conto offshore | Coordinate bancarie e intestatario nelle istruzioni di deposito |

### Minaccia

Il dossier dice che la minaccia nasce da tre variabili ma non le nomina: vanno recuperate dalla matrice originale. In mancanza, propongo queste tre.

- Esposizione verso l'Italia: lingua, valuta, promozione in canali italiani, presenza nell'elenco ADM dei siti inibiti.
- Opacità dell'operatore: nessuna società dichiarata, licenza non verificabile, registrazione del dominio schermata.
- Portata promozionale: numero di canali e annunci che rimandano al sito, pubblico di quei canali.

### Calcolo

Vulnerabilità e minaccia sono medie pesate sui soli indicatori determinati. La quota di indicatori determinati è la copertura, mostrata accanto al punteggio.

```latex
V = \frac{\sum_{i \in D} w_i \, v_i}{\sum_{i \in D} w_i}, \qquad
C = \frac{|D|}{N}
```

Nella formula D è l'insieme degli indicatori determinati, N il loro totale, w il peso, v il valore tra 0 e 1. La minaccia T si calcola allo stesso modo. V e T, divisi in livelli, entrano nella matrice che restituisce la classe di rischio: è il Trust Index della Figura 18 del dossier.

Regole che precedono il calcolo:

- Dominio di un concessionario ADM: escluso dalla valutazione di illegalità.
- Dominio che espone logo o numero di concessione ADM senza comparire nell'elenco: segnalazione immediata, a prescindere dal punteggio.
- Copertura sotto soglia: nessun indice, il sito va all'analista.

### Tenuta nel tempo

- Pesi, soglie e matrice stanno in un file di configurazione versionato. Ogni punteggio registra la versione usata e gli indicatori con le loro evidenze.
- Validazione: l'analista valuta a mano un campione di una cinquantina di siti; si misura la concordanza con la classe automatica e si tarano i pesi.
- Solo dopo, con abbastanza casi validati, ha senso sostituire i pesi fissati a mano con un modello statistico.

Il rating degli eventi sportivi a rischio di combine, citato nel dossier, richiede serie storiche di quote e volumi. Non rientra in questa matrice e lo terrei fuori dal primo ciclo.

## Modello dati e stack tecnologico

Un solo database relazionale e un solo archivio di file sostituiscono i file di testo, CSV e JSON sparsi del 2020.

| Tabella | Contenuto |
| --- | --- |
| sonda | Tipo, configurazione, cursore, stato, ultimo errore |
| elemento grezzo | Messaggio, pagina o file come raccolto, con fonte, data e hash |
| media | Video, audio, immagine, APK collegati a un elemento grezzo |
| estrazione | Testo da OCR, trascrizione o analisi, con tempo e modello usato |
| entità | URL, dominio, marchio, portafoglio, società, licenza, e i legami tra loro |
| sito | Dominio canonico e gruppo di domini gemelli |
| snapshot | Stato di un sito a una data: HTML, schermata, traffico |
| indicatore | Valore, evidenza, certezza, collettore e versione |
| punteggio | Vulnerabilità, minaccia, copertura, Trust Index, versione delle regole |
| revisione | Giudizio dell'analista, correzioni, note |

| Livello | Scelta | Sostituisce |
| --- | --- | --- |
| Codice | Python | Invariato |
| Database | PostgreSQL, con ricerca testuale e vettoriale | File di testo, CSV, fogli |
| File grezzi | Archivio a oggetti compatibile S3 | Cartelle locali |
| Code di lavoro | Celery con Redis; per iniziare basta una tabella di lavori | Avvio manuale degli script |
| Telegram | Telethon | Script del 2019-2020 |
| Crawler | Scrapy con Playwright | pyspider, Selenium, Geckodriver |
| Tor | Demone Tor come proxy SOCKS | Tor Browser automatizzato |
| Video | ffmpeg, PaddleOCR PP-OCRv5 | VidScraper |
| Audio | ffmpeg, faster-whisper | Servizi cloud e passaggi manuali |
| Linguaggio | Modello multilingue pre-addestrato, modello linguistico in locale | ULMFiT, ELMo |
| App Android | MobSF, emulatore ufficiale, proxy di intercettazione | ApkAnalyzer, BlueStacks |
| Console analista | Applicazione web semplice sul database | Lettura manuale dei file |
| Esecuzione | Docker Compose su una macchina con GPU | Macchine virtuali separate |

Crawler, Tor e ambiente di analisi degli APK vivono in una rete separata dal resto. Trattano contenuti ostili e non devono vedere il database se non attraverso la coda.

## Vincoli legali e di conformità

Quattro vincoli cambiano il disegno rispetto al 2020. Non sono un parere legale. La raccolta di dati reali parte comunque da subito, per decisione presa; il confronto con un legale resta consigliato.

- **Telegram.** I termini dell'API vietano di usare o aggregare dati della piattaforma per addestrare, sviluppare o impiegare modelli di intelligenza artificiale ([fonte](https://core.telegram.org/api/terms)). I termini sui contenuti vietano raccolta, indicizzazione e aggregazione a quel fine e, più in generale, ogni accesso ai contenuti degli utenti oltre l'uso ordinario; l'eccezione copre solo i dati necessari a un client legittimo ([fonte](https://telegram.org/tos/content-licensing)). Il prototipo del dossier, che addestra modelli sulle pubblicità raccolte, oggi li violerebbe. Decisione presa: la sonda è attiva da subito, solo su canali e gruppi pubblici e con un account dedicato. Il rischio di blocco dell'account e di contestazione resta. I modelli non vanno addestrati su dati Telegram.
- **Meta.** Nessuno scraping. L'accesso passa dalla Content Library e dai suoi requisiti ([fonte](https://transparency.meta.com/researchtools/meta-content-library)).
- **Dati personali.** Messaggi e profili pubblici contengono dati personali. Si conserva solo ciò che serve a identificare il sito pubblicizzato; autori e membri dei gruppi non si archiviano. Servono base giuridica, valutazione d'impatto e tempi di conservazione.
- **Profilazione di persone.** Legittima solo per chi ha titolo sui dati: il concessionario sui propri clienti, l'autorità in indagine. Il prototipo lavora su dati sintetici.

Altri punti da tenere presenti:

- Se il destinatario sono le forze dell'ordine, il sistema può rientrare tra quelli ad alto rischio del regolamento europeo sull'IA. Gli obblighi per questi sistemi si applicano dal 2 dicembre 2027 ([fonte](https://www.gibsondunn.com/eu-ai-act-omnibus-agreement)). Registri, documentazione e supervisione umana conviene prevederli già nel prototipo.
- Sul dark web l'accesso è solo passivo: nessuna registrazione con identità fittizie, nessun acquisto. Va definito cosa fare se il crawler incontra materiale illecito di altra natura.
- Ogni evidenza porta hash, data e versione dello strumento, così regge un riesame.
- L'elenco ADM dei siti inibiti è pubblico ([fonte](https://www.casinos.com/it/news/estate-bollente-gioco-illegale-multe-chiusure-indagini-globali)). Va verificato il formato in cui si scarica dal portale ADM, che non ho potuto aprire direttamente.

## Piano di realizzazione

Cinque fasi in sequenza; le prime due bastano per avere un prototipo dimostrabile, anche senza alcuna sonda automatica. Ogni fase si chiude con una prova su dati reali.

&#91;embedded content: piano · 5 fasi, ciascuna con il suo criterio di uscita\]

La Fase 1 è evidenziata perché è quella che decide se il progetto regge: se il Trust Index non concorda con l'analista, le sonde alimentano un punteggio di cui nessuno si fida.

- Le fasi 2 e 3 possono procedere in parallelo se le persone sono almeno due.
- La sonda Telegram parte con la Fase 2 senza altre attese: la decisione è presa.
- Durate e date dipendono da team e disponibilità dell'analista: non le ho stimate.

## Rischi e decisioni aperte

Due decisioni sono prese: dati reali fin dall'inizio e sonda Telegram attiva. Ne restano sette aperte; le prime due condizionano il resto.

- [ ] Chi è il destinatario dei prototipi e con quale titolo raccoglie i dati.
- [ ] Definire la base giuridica del trattamento dei dati raccolti.
- [ ] Recuperare la matrice originale a quattro fogli, con i pesi e le tre variabili della minaccia.
- [ ] Verificare se esiste ancora il codice delle sonde Telegram del 2019-2020.
- [ ] Decidere se cercare un partner accademico per l'accesso ai dati Meta.
- [ ] Confermare la disponibilità di una macchina con GPU.
- [ ] Indicare chi farà da analista per etichettare gli esempi e validare i punteggi.

| Rischio | Effetto | Contromisura |
| --- | --- | --- |
| Blocco degli account Telegram | Sonde ferme | Pochi account, frequenze basse, ingresso manuale come riserva |
| I siti cambiano dominio dopo l'inibizione ([fonte](https://www.ilgiorno.it/cronaca/caso-fonbet-pirlo-il-sito-di-scommesse-russo-oscurato-in-italia-weq11p6b)) | Lista URL superata in fretta | Gruppi di domini gemelli, ricontrollo periodico |
| Siti che mostrano cassa e condizioni solo dopo l'accesso | Molti indicatori non determinabili | Copertura dichiarata accanto al punteggio, revisione dell'analista |
| Errori di OCR o trascrizione sugli URL | Falsi siti in lista | Verifica DNS di ogni URL estratto, conferma da una seconda fonte |
| Pesi fissati a giudizio | Trust Index contestabile | Validazione su campione, regole versionate |
| Pagine e APK ostili | Compromissione dell'ambiente | Rete separata, contenitori usa e getta |

## Fonti

- Dossier Soft Strategy S.p.A. 2020, capitolo 4 "Betting" (file caricato).
- [Telegram API Terms of Service](https://core.telegram.org/api/terms)
- [Telegram, Terms of Service for Content Licensing](https://telegram.org/tos/content-licensing)
- [Meta Content Library and API](https://transparency.meta.com/researchtools/meta-content-library)
- [Datashake, Facebook Social Data API in 2026](https://www.datashake.com/blog/facebook-social-data-api-in-2026)
- [Corriere dello Sport, nuove concessioni ADM](https://www.corrieredellosport.it/scommesse/nuovi-siti-scommesse)
- [Casinos.com, un solo sito per operatore dal 13 novembre](https://www.casinos.com/it/news/adm-stretta-skin-13-novembre-un-sito-operatore)
- [Sky TG24, 12.448 domini inibiti da ADM](https://tg24.sky.it/cronaca/2026/07/27/andrea-pirlo-fonbet-sito-scommesse)
- [Il Giorno, spostamento su domini alternativi](https://www.ilgiorno.it/cronaca/caso-fonbet-pirlo-il-sito-di-scommesse-russo-oscurato-in-italia-weq11p6b)
- [Casinos.com, elenco ADM dei siti inibiti](https://www.casinos.com/it/news/estate-bollente-gioco-illegale-multe-chiusure-indagini-globali)
- [Curaçao Gaming Authority, registro delle licenze](https://www.gamingcontrolcuracao.org/en/133i348441001)
- [pyspider su GitHub, archiviato](https://github.com/binux/pyspider)
- [PaddleOCR, PP-OCRv5 multilingue](https://www.paddleocr.ai/v3.5.0/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html)
- [Northflank, modelli di trascrizione aperti 2026](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks)
- [Pinggy, modelli di trascrizione da ospitare in proprio](https://pinggy.io/blog/best_open_source_self_hosted_speech_to_text_models/)
- [AppSecSanta, MobSF](https://appsecsanta.com/mobsf)
- [Gibson Dunn, rinvio degli obblighi ad alto rischio dell'AI Act](https://www.gibsondunn.com/eu-ai-act-omnibus-agreement)
