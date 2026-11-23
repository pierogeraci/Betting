from core.models import EventoSportivo, LegalEntity, Modello
from tests.console.test_portale import login
from tests.core.test_fase4 import _site_with_company


def test_phase4_pages(client, db, store):
    site = _site_with_company(db, "luckymoon.example.com", "Moon Gaming N.V.")
    csrf = login(client)
    page = client.get(f"/siti/{site.id}?scheda=legal").text
    assert "Moon Gaming N.V." in page and "Nessun registro pubblico caricato" in page
    client.post(
        f"/siti/{site.id}/legal", data={"csrf": csrf, "nome": "Moon Gaming N.V.", "decisione": "conferma"}
    )
    assert db.query(LegalEntity).one().stato == "confermata"
    assert '<svg class="grafo"' in client.get(f"/siti/{site.id}?scheda=grafo").text
    for path in ["/app", "/registri", "/eventi", "/anomalie"]:
        assert client.get(path).status_code == 200, path
    client.post("/anomalie", data={"csrf": csrf, "conti": "120", "quota": "0.1", "seme": "1"})
    assert db.query(Modello).filter(Modello.nome == "anomalie").one().metriche["dati"] == "sintetici"
    assert "SINT-" in client.get("/anomalie").text
    csv = (
        "evento;inizio;bookmaker;momento;esito;quota;volume\n"
        + "\n".join(
            f"Alfa-Beta;2026-11-20T20:00:00;{b};2026-11-20T{h:02d}:00:00;1;{q};"
            for b, q in [("A", "2.1"), ("B", "2.05"), ("C", "2.1"), ("D", "1.6")]
            for h in (8, 18)
        )
    ).encode()
    client.post("/eventi", data={"csrf": csrf}, files={"file": ("q.csv", csv, "text/csv")})
    ev = db.query(EventoSportivo).one()
    assert ev.rating in {"medio", "alto"} and "D offre" in client.get(f"/eventi/{ev.id}").text
    upload = client.post(
        "/registri",
        data={"csrf": csrf, "registro": "licenze", "fonte": "x"},
        files={"file": ("r.csv", b"nome\nA", "text/csv")},
    )
    assert upload.status_code == 403


def test_report_includes_legal_entity(client, db, store):
    site = _site_with_company(db, "luckymoon.example.com", "Moon Gaming N.V.")
    csrf = login(client)
    client.post(
        f"/siti/{site.id}/legal", data={"csrf": csrf, "nome": "Moon Gaming N.V.", "decisione": "conferma"}
    )
    report = client.get(f"/siti/{site.id}/report").text
    assert "<h2>Legal entity</h2>" in report and "Moon Gaming N.V." in report
