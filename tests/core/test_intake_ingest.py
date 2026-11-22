import json

import pytest

from core import adm, ingest, intake
from core.domains import InvalidUrl
from core.models import ElementoGrezzo, Entita, Indicatore, Lavoro, Media, Revisione, Sito
from core.storage import sha256_hex

INBOX = "prova-arrivo"


def _drop(store, job_id, manifest, files):
    for name, data in files.items():
        store.put(INBOX, f"{job_id}/{name}", data)
    store.put(INBOX, f"{job_id}/manifesto.json", json.dumps(manifest).encode())


def _manifest(state="riuscito", html=b"<html><title>T</title></html>", shot=b"\x89PNG finto", **extra):
    files = {"pagina.html": html, "schermata.png": shot}
    manifest = {
        "esito": state,
        "url_finale": "https://www.altro-dominio.example.net/home",
        "codice_http": 200,
        "titolo": "T",
        "reindirizzamenti": [
            {"url": "https://sito.example.com/", "codice": 302},
            {"url": "https://www.altro-dominio.example.net/home", "codice": 200},
        ],
        "raccolto_il": "2026-11-16T10:00:00+00:00",
        "strumento": "playwright-chromium",
        "versione_strumento": "1",
        "file": {
            "html": {"nome": "pagina.html", "sha256": sha256_hex(html)},
            "schermata": {"nome": "schermata.png", "sha256": sha256_hex(shot)},
        },
    }
    manifest.update(extra)
    return manifest, files


def test_submit_url_creates_everything_once(db):
    first = intake.submit_url(db, "Sito.Example.com/promo")
    assert not first.already_known
    assert first.site.dominio == "example.com"
    assert (
        first.element.fonte == "manuale"
        and len(first.element.sha256) == 64
        and first.element.raccolto_il.tzinfo
    )
    assert first.job.coda == "raccolta" and first.job.successivo == "acquisisci_snapshot"
    assert {e.tipo for e in db.query(Entita)} == {"url", "dominio"}
    second = intake.submit_url(db, "https://sito.example.com/promo")
    assert second.already_known and second.element.id == first.element.id
    assert db.query(ElementoGrezzo).count() == 1 and db.query(Sito).count() == 1
    assert (
        db.query(Lavoro).filter(Lavoro.tipo == "snapshot").count() == 2
    )  # ogni inserimento chiede un nuovo snapshot


def test_submit_url_rejects_internal(db):
    with pytest.raises(InvalidUrl):
        intake.submit_url(db, "http://archivio:8333/")
    assert db.query(Lavoro).count() == 0


def test_submit_file_archives_by_hash(db, store):
    a = intake.submit_file(db, "../../schermata pubblicità.png", b"contenuto", user_id=None, note="da WeChat")
    assert a.media.tipo == "immagine" and a.media.nome_file == "schermata pubblicità.png"
    assert store.get("prova-grezzi", a.media.oggetto_chiave) == b"contenuto"
    b = intake.submit_file(db, "copia.png", b"contenuto")
    assert b.already_known and db.query(Media).count() == 1
    assert intake.submit_file(db, "app.apk", b"x").media.tipo == "apk"


def test_ingest_snapshot_verifies_and_compares(db, store, fixture_bytes):
    adm.load_list(db, adm.INIBITI, b"altro-dominio.example.net\n")
    sub = intake.submit_url(db, "https://sito.example.com/")
    manifest, files = _manifest()
    _drop(store, sub.job.id, manifest, files)
    snap = ingest.ingest_snapshot(db, sub.job)
    assert snap.stato == "riuscito" and snap.dominio_finale == "www.altro-dominio.example.net"
    assert store.get("prova-grezzi", snap.html_chiave) == files["pagina.html"]
    assert len(snap.sha256) == 64 and snap.raccolto_il.tzinfo is not None
    assert not store.exists(INBOX, f"{sub.job.id}/manifesto.json")  # il secchio di arrivo si svuota
    # Il confronto ADM guarda anche il dominio finale dopo i reindirizzamenti.
    ind = (
        db.query(Indicatore)
        .filter(Indicatore.codice == "dominio_inibito_adm")
        .order_by(Indicatore.id.desc())
        .first()
    )
    assert ind.valore == "presente" and ind.snapshot_id == snap.id
    assert ind.evidenza["dominio_confrontato"] == "altro-dominio.example.net"
    assert sub.site.esito_adm == "inibito"


def test_ingest_rejects_wrong_hash(db, store):
    sub = intake.submit_url(db, "https://sito.example.com/")
    manifest, files = _manifest()
    files["pagina.html"] = b"contenuto alterato"
    _drop(store, sub.job.id, manifest, files)
    with pytest.raises(ingest.IngestError, match="Hash"):
        ingest.ingest_snapshot(db, sub.job)


def test_blocked_page_goes_to_manual_review(db, store):
    sub = intake.submit_url(db, "https://sito.example.com/")
    manifest, files = _manifest(state="bloccato", motivo="captcha", codice_http=403)
    _drop(store, sub.job.id, manifest, files)
    snap = ingest.ingest_snapshot(db, sub.job)
    review = db.query(Revisione).one()
    assert (review.tipo, review.stato, review.snapshot_id) == ("pagina_bloccata", "aperta", snap.id)


def test_error_snapshot_without_files(db, store):
    sub = intake.submit_url(db, "https://sito.example.com/")
    _drop(store, sub.job.id, {"esito": "errore", "errore": "net::ERR_NAME_NOT_RESOLVED", "file": {}}, {})
    snap = ingest.ingest_snapshot(db, sub.job)
    assert snap.stato == "errore" and snap.html_chiave is None and "NAME_NOT_RESOLVED" in snap.errore
