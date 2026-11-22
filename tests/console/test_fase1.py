from core import profiling, worker
from core.models import Puntata, Revisione
from tests.console.test_portale import login
from tests.core.test_profiling import drop_snapshot


def full_site(db, store):
    site, _ = drop_snapshot(
        db, store, "https://www.luckymoon.example.com/", "crypto_home.html", hosts=["www.skrill.com"]
    )
    drop_snapshot(
        db,
        store,
        "https://www.luckymoon.example.com/terms-and-conditions",
        "crypto_terms.html",
        secondary=True,
    )
    profiling.profile_site(db, site)
    return site


def test_profile_tabs_and_report(client, db, store):
    site = full_site(db, store)
    login(client)
    base = f"/siti/{site.id}"
    prof = client.get(base + "?scheda=profilazione").text
    assert "Pagamento e puntata in criptovalute" in prof and "bc1qar0srrr7" in prof and "Slot" in prof
    trust = client.get(base + "?scheda=trust").text
    assert "Calcolo della vulnerabilità" in trust and "mancano i dati di puntata" in trust
    assert "Senza indice" in client.get("/siti").text
    report = client.get(base + "/report")
    assert report.status_code == 200 and "Report di intelligence" in report.text
    assert "script-src" not in report.headers["content-security-policy"]
    assert "attachment" in client.get(base + "/report?scarica=1").headers["content-disposition"]
    for tab in ["puntate", "gemelli"]:
        assert client.get(f"{base}?scheda={tab}").status_code == 200


def test_bets_upload_and_judgement(client, db, store):
    site = full_site(db, store)
    csrf = login(client)
    csv = b"importo_puntato,importo_vinto,momento\n3,24,2026-11-01T10:00:00\n1000,2,2026-11-01T10:01:00\n5,0,2026-11-01T10:02:00\n100,59,2026-11-01T10:03:00\n10,67,2026-11-01T10:04:00\n"
    response = client.post(
        f"/siti/{site.id}/puntate", data={"csrf": csrf}, files={"file": ("p.csv", csv, "text/csv")}
    )
    assert response.status_code == 303 and db.query(Puntata).filter(Puntata.fonte == "caricata").count() == 5
    # Esegue il ricalcolo in coda nella stessa transazione di prova.
    for job in db.query(worker.Lavoro).filter(worker.Lavoro.tipo == "punteggio"):
        worker.HANDLERS["punteggio"](db, job)
    trust = client.get(f"/siti/{site.id}?scheda=trust").text
    assert "Raffinamento dei dati" in trust and "Rischio alto" in trust
    assert (
        client.post(
            f"/siti/{site.id}/giudizio", data={"csrf": csrf, "classe": "alto", "note": " "}
        ).status_code
        == 303
    )
    assert not db.query(Revisione).filter(Revisione.tipo == "giudizio").count()
    client.post(
        f"/siti/{site.id}/giudizio",
        data={"csrf": csrf, "classe": "alto", "note": "Cassa in BTC e nessun KYC verificati a mano."},
    )
    page = client.get("/validazione").text
    assert "example.com" in page and "Concorda" in page and "100%" in page


def test_sites_filter_by_class(client, db, store):
    full_site(db, store)
    login(client)
    assert "/siti/" in client.get("/siti?classe=nessun_indice").text
    assert "Nessun sito corrisponde" in client.get("/siti?classe=alto").text
