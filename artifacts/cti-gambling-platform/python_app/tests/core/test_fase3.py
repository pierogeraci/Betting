import hashlib
import json

from core import analysis, intake
from core.media_jobs import ingest_extraction, request_extraction
from core.models import ElementoGrezzo, Entita, Estrazione, Etichetta, Lavoro, Modello, Sito, Valutazione


def test_upload_media_goes_to_extraction_and_back(db, store):
    sub = intake.submit_file(db, "pubblicita.mp4", b"video finto", note="da WeChat")
    job = db.query(Lavoro).filter(Lavoro.tipo == "estrai_media").one()
    assert job.coda == "raccolta" and store.exists("betting-lavorazione", job.carico["chiave"])
    assert request_extraction(db, sub.media) is None  # già in coda
    frame = b"\xff\xd8 jpg"
    manifest = {
        "esito": "riuscito",
        "estrazioni": [
            {
                "tipo": "ocr",
                "testo": "BONUS 200% scommesse su vincitutto-bet.com",
                "inizio_ms": 1500,
                "modello": "PP-OCRv5",
            },
            {
                "tipo": "trascrizione",
                "testo": "gioca ora su vincitutto bet punto com",
                "inizio_ms": 0,
                "fine_ms": 4000,
                "modello": "faster-whisper",
            },
            {"tipo": "qr", "testo": "https://vincitutto-bet.com/r/qr", "inizio_ms": 1500},
            {"tipo": "comando", "testo": "rm -rf /"},
        ],
        "fotogrammi": [{"nome": "fotogramma_00001500.jpg", "sha256": hashlib.sha256(frame).hexdigest()}],
        "info": {"fotogrammi": 1},
    }
    store.put("prova-arrivo", f"{job.id}/fotogramma_00001500.jpg", frame)
    store.put("prova-arrivo", f"{job.id}/manifesto.json", json.dumps(manifest).encode())
    out = ingest_extraction(db, job)
    assert out == {"estrazioni": 3, "fotogrammi": 1}  # il tipo sconosciuto è scartato
    assert not store.exists("betting-lavorazione", job.carico["chiave"])
    analysis_job = db.query(Lavoro).filter(Lavoro.tipo == "analizza_testo").one()
    result = analysis.analyse_element(db, db.get(ElementoGrezzo, analysis_job.carico["elemento_id"]))
    assert result["siti_nuovi"] == 1 and db.query(Sito).one().dominio == "vincitutto-bet.com"
    an = db.query(Estrazione).filter(Estrazione.tipo == "analisi").one()
    assert "vincitutto-bet.com" in an.metadati["campi"]["domini"] and an.metadati["classificazione"] is None


def _labelled(db, n, source):
    for i in range(n):
        text = (
            f"Bonus casino {i} scommesse slot giri gratis" if i % 2 else f"Notizie meteo e ricette numero {i}"
        )
        el = ElementoGrezzo(
            fonte=source,
            tipo="messaggio",
            riferimento=f"r{source}{i}",
            contenuto=text,
            sha256=hashlib.sha256(f"{source}{i}".encode()).hexdigest(),
        )
        db.add(el)
        db.flush()
        db.add(
            Etichetta(
                elemento_grezzo_id=el.id,
                pubblicita_gioco=bool(i % 2),
                entita={"attese": [], "verificate": True},
            )
        )
    db.flush()


def test_training_excludes_telegram_and_records_metrics(db, store):
    _labelled(db, 30, "web")
    _labelled(db, 10, "telegram")
    out = analysis.train_classifier(db)
    model = db.query(Modello).filter(Modello.nome == "classificatore", Modello.attivo.is_(True)).one()
    assert model.metriche["telegram_esclusi"] == 10 and model.metriche["esempi_addestramento"] == 30
    assert model.metriche["motore"] in {"tfidf", "vettori"} and "precisione" in out
    assert db.query(Valutazione).filter(Valutazione.ambito == "classificatore").count() == 1
    # Con il modello attivo l'analisi riporta la classificazione.
    el = db.query(ElementoGrezzo).filter(ElementoGrezzo.fonte == "web").first()
    analysis.analyse_element(db, el)
    an = (
        db.query(Estrazione)
        .filter(Estrazione.elemento_grezzo_id == el.id, Estrazione.tipo == "analisi")
        .one()
    )
    assert an.metadati["classificazione"]["modello"] == model.versione


def test_entity_evaluation(db):
    el = ElementoGrezzo(
        fonte="web",
        tipo="pagina",
        riferimento="x",
        contenuto="Gioca su vincitutto-bet.com e altro-sito.net",
        sha256="e" * 64,
    )
    db.add(el)
    db.flush()
    db.add(
        Etichetta(
            elemento_grezzo_id=el.id,
            pubblicita_gioco=True,
            entita={"attese": [{"tipo": "dominio", "valore": "vincitutto-bet.com"}], "verificate": True},
        )
    )
    db.flush()
    m = analysis.evaluate_entities(db)
    assert m["richiamo"] == 1.0 and m["precisione"] == 0.5


def test_topics(db):
    for i in range(12):
        text = (
            "bonus casino slot giri gratis deposito "
            if i % 2
            else "calcio serie partita squadra gol allenatore "
        ) * 3
        db.add(
            ElementoGrezzo(
                fonte="web",
                tipo="pagina",
                riferimento=f"t{i}",
                contenuto=text + str(i),
                sha256=hashlib.sha256(f"t{i}".encode()).hexdigest(),
            )
        )
    db.flush()
    assert analysis.compute_topics(db)["argomenti"] >= 2
    assert db.query(Modello).filter(Modello.nome == "argomenti").one().metriche["argomenti"][0]["parole"]
    assert db.query(Entita).count() == 0


def test_telegram_content_never_trains(db, store):
    _labelled(db, 30, "web")
    # Contenuti Telegram arrivati per altre vie: riferimento t.me o provenienza dichiarata.
    for i in range(6):
        el = ElementoGrezzo(
            fonte="web",
            tipo="pagina",
            riferimento=f"https://t.me/s/canale/{i}",
            contenuto="bonus casino slot",
            sha256=hashlib.sha256(f"tme{i}".encode()).hexdigest(),
        )
        db.add(el)
        db.flush()
        db.add(Etichetta(elemento_grezzo_id=el.id, pubblicita_gioco=True, entita={}))
    up = intake.submit_file(db, "screen.png", b"png finto", provenance="telegram")
    db.add(Etichetta(elemento_grezzo_id=up.element.id, pubblicita_gioco=True, entita={}))
    db.flush()
    assert analysis.training_source(up.element) == "telegram"
    analysis.train_classifier(db)
    model = db.query(Modello).filter(Modello.nome == "classificatore", Modello.attivo.is_(True)).one()
    assert model.metriche["esempi_addestramento"] == 30 and model.metriche["telegram_esclusi"] == 6


def test_topics_exclude_telegram(db):
    for i in range(12):
        db.add(
            ElementoGrezzo(
                fonte="telegram",
                tipo="messaggio",
                riferimento=f"https://t.me/c/{i}",
                contenuto="bonus casino slot giri gratis " * 3,
                sha256=hashlib.sha256(f"tg{i}".encode()).hexdigest(),
            )
        )
    db.flush()
    assert analysis.compute_topics(db)["documenti"] == 0


def test_channel_names_not_stored_in_analysis(db, store):
    el = ElementoGrezzo(
        fonte="web",
        tipo="pagina",
        riferimento="x",
        contenuto="scrivi a t.me/supporto_mario per il bonus casino",
        sha256="f" * 64,
    )
    db.add(el)
    db.flush()
    analysis.analyse_element(db, el)
    an = db.query(Estrazione).filter(Estrazione.tipo == "analisi").one()
    assert "supporto_mario" not in json.dumps(an.metadati) and an.metadati["campi"]["canali"] == 1
