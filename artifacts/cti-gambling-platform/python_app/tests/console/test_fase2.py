from core.models import Avviso, Canale, Lavoro, ParolaChiave, Sonda
from tests.console.test_portale import login


def test_probe_pages_and_admin_actions(client, db):
    csrf = login(client)
    page = client.get("/sonde").text
    assert "La lista URL cresce da sola?" in page and "Telegram" in page
    assert "Worker isolato non collegato" in page
    web = db.query(Sonda).filter(Sonda.nome == "web").one()
    assert (
        client.post(f"/sonde/{web.id}/stato", data={"csrf": csrf}).status_code == 403
    )  # solo amministratori
    client.cookies.clear()
    csrf = login(client, "capo")
    bad = client.post(
        f"/sonde/{web.id}/configura",
        data={"csrf": csrf, "semi": "http://127.0.0.1/\nhttps://dir.example.org/"},
    )
    assert bad.status_code == 303 and web.configurazione.get("semi") in (None, [])
    client.post(
        f"/sonde/{web.id}/configura",
        data={
            "csrf": csrf,
            "semi": "https://dir.example.org/",
            "intervallo_minuti": "1",
            "max_pagine": "999",
        },
    )
    assert (
        web.configurazione["semi"] == ["https://dir.example.org/"]
        and web.configurazione["intervallo_minuti"] == 15
    )
    assert web.configurazione["max_pagine"] == 200
    client.post(f"/sonde/{web.id}/esegui", data={"csrf": csrf})
    assert db.query(Lavoro).filter(Lavoro.tipo == "crawl").count() == 1
    tor = db.query(Sonda).filter(Sonda.nome == "tor").one()
    client.post(f"/sonde/{tor.id}/configura", data={"csrf": csrf, "semi": "https://clearweb.example.com/"})
    assert not tor.configurazione.get("semi")


def test_channels_keywords_alerts(client, db):
    csrf = login(client)
    assert client.post("/canali", data={"csrf": csrf, "nome": "https://t.me/+AbCdEf"}).status_code == 303
    assert db.query(Canale).count() == 0  # link d'invito rifiutato
    client.post("/canali", data={"csrf": csrf, "nome": "@Scommesse_VIP"})
    ch = db.query(Canale).one()
    assert ch.identificativo == "scommesse_vip" and ch.stato == "da_approvare"
    client.post(f"/canali/{ch.id}/approva", data={"csrf": csrf})
    assert ch.stato == "attivo" and ch.approvato_da
    assert "scommesse_vip" in client.get("/canali?stato=attivo").text
    client.post("/parole", data={"csrf": csrf, "termine": "  Quote   Maggiorate ", "avviso": "1"})
    kw = db.query(ParolaChiave).filter(ParolaChiave.termine == "quote maggiorate").one()
    assert kw.avviso
    client.post(f"/parole/{kw.id}/attiva", data={"csrf": csrf})
    assert not kw.attiva
    db.add(Avviso(tipo="parola_chiave", titolo="telegram: «partite truccate»", testo="..."))
    db.flush()
    page = client.get("/").text
    assert 'class="punto-avviso">1<' in page
    assert "partite truccate" in client.get("/avvisi").text
    client.post("/avvisi/letti", data={"csrf": csrf})
    assert "Nessun avviso da leggere" in client.get("/avvisi").text
