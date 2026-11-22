import json

from core import scheduler
from core.ingest_probes import ingest_crawl, ingest_telegram
from core.models import Avviso, Canale, ElementoGrezzo, Lavoro, ParolaChiave, Sito, Sonda
from core.queue import COLLECT, enqueue


def probe(db, name):
    return db.query(Sonda).filter(Sonda.nome == name).one()


def drop(store, job_id, manifest, files=None):
    for n, d in (files or {}).items():
        store.put("prova-arrivo", f"{job_id}/{n}", d)
    store.put("prova-arrivo", f"{job_id}/manifesto.json", json.dumps(manifest).encode())


def test_scheduler_needs_channels_and_respects_state(db, monkeypatch):
    tg = probe(db, "telegram")
    assert tg.stato == "in_pausa"
    job, msg = scheduler.run_probe(db, tg)
    assert job is None and "canali" in msg
    db.add(Canale(identificativo="scommesse_vip", stato="attivo", cursore=10))
    db.flush()
    job, _ = scheduler.run_probe(db, tg)
    assert (
        job.coda == "raccolta"
        and job.carico["canali"][0]["cursore"] == 10
        and "scommesse" in job.carico["parole"]
    )
    assert scheduler.run_probe(db, tg)[0] is None  # già in coda
    monkeypatch.setenv("TELEGRAM_PROBE_ENABLED", "false")
    assert "spenta" in scheduler.run_probe(db, tg)[1]


def test_tick_runs_only_active_and_due(db):
    web = probe(db, "web")
    web.configurazione = {"semi": ["https://dir.example.org/"], "intervallo_minuti": 60}
    assert scheduler.tick(db) == []  # in pausa
    web.stato = "attiva"
    assert scheduler.tick(db) == ["web"]
    db.query(Lavoro).delete()
    assert scheduler.tick(db) == []  # appena eseguita


def test_ingest_telegram_creates_sites_channels_and_alerts(db, store):
    tg = probe(db, "telegram")
    ch = Canale(identificativo="scommesse_vip", stato="attivo", cursore=10)
    db.add(ch)
    db.add(Canale(identificativo="supporto_mario", stato="da_approvare"))
    db.flush()
    db.query(ParolaChiave).filter(ParolaChiave.termine == "partite truccate").one().avviso = True
    job = enqueue(
        db, queue=COLLECT, kind="telegram", payload={"sonda_id": tg.id}, next_kind="acquisisci_telegram"
    )
    image = b"\xff\xd8 immagine"
    import hashlib

    manifest = {
        "esito": "riuscito",
        "attesa": 0,
        "cursori": {str(ch.id): 13},
        "canali": {str(ch.id): {"titolo": "Scommesse VIP", "tipo": "canale", "partecipanti": 1500}},
        "messaggi": [
            {
                "canale_id": ch.id,
                "canale": "scommesse_vip",
                "id": 11,
                "data": "2026-11-20T10:00:00+00:00",
                "testo": "🎰 Bonus casino su vincitutto-bet.com e t.me/altro_canale_bet",
                "link": [],
                "media": [
                    {
                        "nome": "m_1_11.jpg",
                        "sha256": hashlib.sha256(image).hexdigest(),
                        "tipo": "immagine",
                        "mime": "image/jpeg",
                    }
                ],
            },
            {
                "canale_id": ch.id,
                "canale": "scommesse_vip",
                "id": 12,
                "testo": "Partite truccate garantite",
                "link": ["https://fixed-match.example.net/"],
            },
            {
                "canale_id": ch.id,
                "canale": "scommesse_vip",
                "id": 13,
                "testo": "Buongiorno a tutti, oggi su meteo.example.com",
                "link": [],
            },
        ],
    }
    drop(store, job.id, manifest, {"m_1_11.jpg": image})
    stats = ingest_telegram(db, job)
    assert stats["elementi"] == 3 and stats["siti_nuovi"] == 2
    domains = {s.dominio: s for s in db.query(Sito)}
    assert set(domains) == {
        "vincitutto-bet.com",
        "example.net",
    }  # il messaggio senza parole chiave non crea siti
    assert domains["vincitutto-bet.com"].fonte_scoperta == "telegram"
    assert ch.cursore == 13 and ch.partecipanti == 1500
    assert db.query(Canale).filter(Canale.identificativo == "altro_canale_bet").one().stato == "da_approvare"
    assert db.query(Avviso).filter(Avviso.tipo == "parola_chiave").count() == 1
    assert db.query(Lavoro).filter(Lavoro.tipo == "estrai_media").count() == 1
    el = db.query(ElementoGrezzo).filter(ElementoGrezzo.fonte == "telegram").first()
    assert el.riferimento.startswith("https://t.me/scommesse_vip/") and "autore" not in json.dumps(
        el.metadati
    )
    # Seconda acquisizione dello stesso messaggio: nessun duplicato.
    job2 = enqueue(
        db, queue=COLLECT, kind="telegram", payload={"sonda_id": tg.id}, next_kind="acquisisci_telegram"
    )
    drop(store, job2.id, manifest | {"messaggi": manifest["messaggi"][1:2]})
    assert ingest_telegram(db, job2)["duplicati"] == 1


def test_non_public_channel_name_is_erased(db, store):
    tg = probe(db, "telegram")
    ch = Canale(identificativo="supporto_mario", stato="attivo")
    db.add(ch)
    db.flush()
    job = enqueue(
        db, queue=COLLECT, kind="telegram", payload={"sonda_id": tg.id}, next_kind="acquisisci_telegram"
    )
    drop(
        store,
        job.id,
        {
            "esito": "riuscito",
            "messaggi": [],
            "cursori": {},
            "attesa": 0,
            "canali": {str(ch.id): {"errore": "Non è un canale o gruppo pubblico: escluso"}},
        },
    )
    ingest_telegram(db, job)
    assert (
        ch.stato == "rifiutato"
        and ch.identificativo.startswith("rimosso-")
        and "mario" not in ch.identificativo
    )


def test_flood_wait_sets_probe_pause(db, store):
    tg = probe(db, "telegram")
    job = enqueue(
        db, queue=COLLECT, kind="telegram", payload={"sonda_id": tg.id}, next_kind="acquisisci_telegram"
    )
    drop(store, job.id, {"esito": "riuscito", "messaggi": [], "cursori": {}, "canali": {}, "attesa": 900})
    ingest_telegram(db, job)
    assert tg.disponibile_dal is not None
    assert "attendere" in scheduler.run_probe(db, tg)[1]


def test_new_sites_cap(db, store):
    web = probe(db, "web")
    web.configurazione = {"max_siti_nuovi": 2}
    job = enqueue(db, queue=COLLECT, kind="crawl", payload={"sonda_id": web.id}, next_kind="acquisisci_crawl")
    links = [f"https://casino-{i}.example-bet.org/" for i in range(5)] + [
        f"https://sito{i}.com/" for i in range(5)
    ]
    drop(
        store,
        job.id,
        {
            "esito": "riuscito",
            "pagine": [
                {
                    "url": "https://dir.example.org/",
                    "codice_http": 200,
                    "testo": "Elenco casino e scommesse",
                    "sha256": "a" * 64,
                    "link_esterni": links,
                },
                {
                    "url": "https://dir.example.org/bloccata",
                    "codice_http": 403,
                    "testo": "",
                    "sha256": "b" * 64,
                    "bloccato": "accesso_negato",
                    "link_esterni": links,
                },
            ],
        },
    )
    stats = ingest_crawl(db, job)
    assert stats["siti_nuovi"] == 2 and stats["siti_oltre_tetto"] >= 1
    assert any("bloccate" in e for e in stats["errori"])
    assert {s.fonte_scoperta for s in db.query(Sito)} == {"web"}
