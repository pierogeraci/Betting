import json
import re

from core import adm, ingest, intake
from core.models import Lavoro, Revisione, Sito
from core.storage import sha256_hex

PASSWORD = "password-di-prova-123"


def login(client, user="anna"):
    response = client.post("/accesso", data={"nome_utente": user, "password": PASSWORD})
    assert response.status_code == 303
    page = client.get("/")
    return re.search(r'name="csrf" content="([^"]+)"', page.text).group(1)


def snapshot_for(
    db,
    store,
    url,
    state="riuscito",
    html=b"<html><title>Casino</title><script>alert(1)</script></html>",
    **extra,
):
    sub = intake.submit_url(db, url)
    har = json.dumps(
        {
            "log": {
                "entries": [
                    {
                        "request": {"method": "GET", "url": url},
                        "response": {"status": 200, "content": {"mimeType": "text/html"}},
                    },
                    {
                        "request": {"method": "GET", "url": "https://pagamenti.terzi.example.net/sdk.js"},
                        "response": {"status": 200, "content": {"mimeType": "text/javascript"}},
                    },
                ]
            }
        }
    ).encode()
    files = {"pagina.html": html, "schermata.png": b"\x89PNG\r\n\x1a\n finta", "traffico.har": har}
    manifest = {
        "esito": state,
        "url_finale": url,
        "codice_http": 200,
        "titolo": "Casino",
        "raccolto_il": "2026-11-16T10:00:00+00:00",
        "file": {
            "html": {"nome": "pagina.html", "sha256": sha256_hex(html)},
            "schermata": {"nome": "schermata.png", "sha256": sha256_hex(files["schermata.png"])},
            "traffico": {"nome": "traffico.har", "sha256": sha256_hex(har)},
        },
    } | extra
    for name, data in files.items():
        store.put("prova-arrivo", f"{sub.job.id}/{name}", data)
    store.put("prova-arrivo", f"{sub.job.id}/manifesto.json", json.dumps(manifest).encode())
    return sub, ingest.ingest_snapshot(db, sub.job)


def test_pages_require_login(client):
    for path in ["/", "/siti", "/nuovo", "/adm", "/lavori", "/archivio", "/revisioni", "/utenti"]:
        response = client.get(path)
        assert response.status_code == 303 and response.headers["location"] == "/accesso", path
    assert client.get("/salute").json() == {"stato": "ok"}


def test_login_failure_and_lockout(client, db):
    for _ in range(5):
        assert (
            client.post("/accesso", data={"nome_utente": "anna", "password": "sbagliata"}).status_code == 401
        )
    # Dopo cinque errori anche la password giusta è rifiutata.
    assert client.post("/accesso", data={"nome_utente": "anna", "password": PASSWORD}).status_code == 401


def test_security_headers_and_cookie(client):
    response = client.post("/accesso", data={"nome_utente": "anna", "password": PASSWORD})
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie
    page = client.get("/")
    assert "script-src 'self'" in page.headers["content-security-policy"]
    assert page.headers["x-content-type-options"] == "nosniff"
    assert "style=" not in page.text  # nessuno stile in linea: la politica lo vieta


def test_post_without_csrf_is_rejected(client, db):
    login(client)
    assert client.post("/nuovo/url", data={"urls": "https://sito.example.com"}).status_code == 403
    assert db.query(Sito).count() == 0


def test_submit_url_flow(client, db):
    csrf = login(client)
    response = client.post("/nuovo/url", data={"urls": "sito.example.com/promo", "csrf": csrf})
    assert response.status_code == 303
    site = db.query(Sito).one()
    assert response.headers["location"] == f"/siti/{site.id}"
    page = client.get(f"/siti/{site.id}")
    assert "Analisi in corso" in page.text and "Snapshot della pagina" in page.text
    assert db.query(Lavoro).filter(Lavoro.tipo == "snapshot").one().creato_da is not None


def test_submit_many_urls_reports_rejections(client, db):
    csrf = login(client)
    response = client.post(
        "/nuovo/url", data={"urls": "uno.example.com\nhttp://127.0.0.1/\ndue.example.org", "csrf": csrf}
    )
    assert response.status_code == 200
    assert "Rifiutato" in response.text and "indirizzo IP" in response.text
    assert db.query(Sito).count() == 2
    too_many = "\n".join(f"s{i}.example.com" for i in range(26))
    assert client.post("/nuovo/url", data={"urls": too_many, "csrf": csrf}).status_code == 400


def test_site_pages_and_safe_snapshot_views(client, db, store):
    adm.load_list(db, adm.INIBITI, b"casino-finto.net\n")
    sub, snap = snapshot_for(db, store, "https://www.casino-finto.net/")
    login(client)
    site = f"/siti/{sub.site.id}"
    overview = client.get(site)
    assert "Inibito da ADM" in overview.text and "Elenco dei siti inibiti" in overview.text
    assert "non determinabile" in overview.text.lower()  # elenco concessionari non caricato
    assert client.get("/siti?q=casino").text.count("casino-finto.net") >= 1
    assert "Nessun sito corrisponde" in client.get("/siti?esito=concessionario").text
    # Il sorgente è mostrato come testo: il tag script è neutralizzato.
    source = client.get(site + "?scheda=sorgente").text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in source and "<script>alert(1)" not in source
    assert 'sandbox=""' in source
    isolated = client.get(f"/snapshot/{snap.id}/isolato")
    assert isolated.headers["content-security-policy"].startswith("sandbox; default-src 'none'")
    traffic = client.get(site + "?scheda=traffico").text
    assert "pagamenti.terzi.example.net" in traffic and "Terza parte" in traffic
    image = client.get(f"/snapshot/{snap.id}/schermata")
    assert image.headers["content-type"] == "image/png"
    download = client.get(f"/snapshot/{snap.id}/file/html")
    assert (
        download.headers["content-type"] == "application/octet-stream"
        and "attachment" in download.headers["content-disposition"]
    )
    for tab in ["snapshot", "origine", "lavori"]:
        assert client.get(f"{site}?scheda={tab}").status_code == 200


def test_review_queue(client, db, store):
    sub, snap = snapshot_for(
        db, store, "https://sito-bloccato.org/", state="bloccato", motivo="captcha", codice_http=403
    )
    csrf = login(client)
    review = db.query(Revisione).one()
    assert "sito-bloccato.org" in client.get("/revisioni").text
    assert client.post(f"/revisioni/{review.id}/prendi", data={"csrf": csrf}).status_code == 303
    assert review.stato == "in_carico"
    # Senza nota non si chiude.
    assert (
        client.post(
            f"/revisioni/{review.id}/chiudi", data={"csrf": csrf, "esito": "da_riprovare", "note": " "}
        ).status_code
        == 400
    )
    before = db.query(Lavoro).filter(Lavoro.tipo == "snapshot").count()
    assert (
        client.post(
            f"/revisioni/{review.id}/chiudi",
            data={"csrf": csrf, "esito": "da_riprovare", "note": "Aperto a mano: ora risponde."},
        ).status_code
        == 303
    )
    assert review.stato == "chiusa" and review.chiusa_da is not None
    assert db.query(Lavoro).filter(Lavoro.tipo == "snapshot").count() == before + 1


def test_adm_upload_admin_only_and_search(client, db, fixture_bytes):
    csrf = login(client)
    files = {"file": ("inibiti.txt", fixture_bytes("adm/siti_inibiti.txt"), "text/plain")}
    assert (
        client.post("/adm/carica", data={"csrf": csrf, "elenco": "siti_inibiti"}, files=files).status_code
        == 403
    )
    client.cookies.clear()
    csrf = login(client, "capo")
    assert (
        client.post("/adm/carica", data={"csrf": csrf, "elenco": "siti_inibiti"}, files=files).status_code
        == 303
    )
    page = client.get("/adm").text
    assert "Aggiornato" in page and "Mancante" in page
    found = client.get("/adm/cerca?dominio=casino-prova.net", headers={"HX-Request": "true"}).text
    assert "Inibito da ADM" in found and "Riga 3" in found
    bad = client.post(
        "/adm/carica",
        data={"csrf": csrf, "elenco": "siti_inibiti"},
        files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert bad.status_code == 400 and "PDF" in bad.text


def test_file_upload_and_download(client, db):
    csrf = login(client)
    response = client.post(
        "/nuovo/file",
        data={"csrf": csrf, "nota": "schermata da WeChat"},
        files={"file": ("pagina.html", b"<script>alert(1)</script>", "text/html")},
    )
    assert response.status_code == 303
    detail = client.get(response.headers["location"]).text
    assert "schermata da WeChat" in detail
    media_id = re.search(r"/media/(\d+)/scarica", detail).group(1)
    download = client.get(f"/media/{media_id}/scarica")
    # Un HTML caricato non viene mai servito come pagina.
    assert (
        download.headers["content-type"] == "application/octet-stream"
        and "attachment" in download.headers["content-disposition"]
    )


def test_users_admin_only(client, db):
    csrf = login(client)
    assert client.get("/utenti").status_code == 403
    assert "?stato=aperte" in client.get("/revisioni").text and "?stato=fallito" in client.get("/lavori").text
    client.cookies.clear()
    csrf = login(client, "capo")
    assert (
        client.post("/utenti", data={"csrf": csrf, "nome_utente": "nuovo", "password": "corta"}).status_code
        == 400
    )
    assert (
        client.post("/utenti", data={"csrf": csrf, "nome_utente": "nuovo", "password": PASSWORD}).status_code
        == 303
    )
    assert "nuovo" in client.get("/utenti").text


def test_other_pages_render(client, db):
    login(client)
    for path in [
        "/lavori",
        "/archivio",
        "/revisioni",
        "/profilo",
        "/nuovo",
        "/cruscotto/riepilogo",
        "/siti/999999",
    ]:
        assert client.get(path).status_code in {200, 404}, path
    assert "Pagina non trovata" in client.get("/siti/999999").text
