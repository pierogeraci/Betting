import hashlib

from core.models import ElementoGrezzo, EmojiSignificato, Estrazione, Etichetta, Lavoro
from tests.console.test_portale import login


def element(db, text, source="web"):
    el = ElementoGrezzo(
        fonte=source,
        tipo="messaggio",
        riferimento="https://t.me/c/1",
        contenuto=text,
        sha256=hashlib.sha256(text.encode()).hexdigest(),
    )
    db.add(el)
    db.flush()
    return el


def test_labelling_flow(client, db):
    el = element(db, "Bonus 200% su vincitutto-bet.com")
    db.add(
        Estrazione(
            elemento_grezzo_id=el.id, tipo="ocr", testo="SCRITTA NEL VIDEO bonus", tempo_inizio_ms=65000
        )
    )
    db.flush()
    csrf = login(client)
    page = client.get(f"/archivio/{el.id}").text
    assert "Testo nei fotogrammi (OCR)" in page and "1:05" in page
    assert "Bonus 200%" in client.get("/etichettatura").text
    bad = client.post(
        f"/archivio/{el.id}/etichetta", data={"csrf": csrf, "gioco": "si", "entita": "senza due punti"}
    )
    assert bad.status_code == 303 and not db.query(Etichetta).count()
    client.post(
        f"/archivio/{el.id}/etichetta",
        data={
            "csrf": csrf,
            "gioco": "si",
            "entita": "dominio: vincitutto-bet.com",
            "torna": "/etichettatura",
        },
    )
    lab = db.query(Etichetta).one()
    assert lab.pubblicita_gioco and lab.entita["attese"] == [
        {"tipo": "dominio", "valore": "vincitutto-bet.com"}
    ]
    assert "Niente da etichettare" in client.get("/etichettatura").text
    assert client.get(f"/archivio/{el.id}/testo?tipo=ocr").text == "[1:05] SCRITTA NEL VIDEO bonus"


def test_search_and_pages(client, db):
    el = element(db, "messaggio qualunque")
    db.add(
        Estrazione(
            elemento_grezzo_id=el.id,
            tipo="trascrizione",
            testo="deposita in bitcoin e vinci",
            tempo_inizio_ms=12000,
        )
    )
    db.flush()
    csrf = login(client)
    found = client.get("/ricerca-contenuti?q=bitcoin").text
    assert "trascrizione" in found and "0:12" in found
    assert "Nessun risultato" in client.get("/ricerca-contenuti?q=parolainesistente").text
    assert "Dizionario delle emoji" in client.get("/emoji").text
    assert "Argomenti non ancora calcolati" in client.get("/argomenti").text
    client.post("/argomenti", data={"csrf": csrf})
    assert db.query(Lavoro).filter(Lavoro.tipo == "argomenti").count() == 1
    assert "Nessuna valutazione ancora" in client.get("/valutazione").text
    assert client.post("/valutazione/addestra", data={"csrf": csrf}).status_code == 403
    client.post(f"/archivio/{el.id}/analizza", data={"csrf": csrf})
    assert db.query(Lavoro).filter(Lavoro.tipo == "analizza_testo").count() == 1


def test_emoji_admin(client, db):
    client.cookies.clear()
    csrf = login(client, "capo")
    client.post(
        "/emoji",
        data={
            "csrf": csrf,
            "carattere": "🎰",
            "piattaforma": "",
            "significato": "slot machine",
            "categoria": "casino",
        },
    )
    assert (
        db.query(EmojiSignificato)
        .filter(EmojiSignificato.carattere == "🎰", EmojiSignificato.piattaforma == "")
        .one()
        .significato
        == "slot machine"
    )
