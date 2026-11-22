import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from core import apk, intake, legal, profiling
from core.models import Estrazione, Indicatore, Lavoro, LegalEntity, LegameSito, Sito
from probes.apk.dynamic import flows_summary
from probes.apk.static import summarize
from scoring import anomalies, events

F = Path(__file__).resolve().parent.parent / "fixtures"


def test_mobsf_summary():
    s = summarize(json.loads((F / "apk/rapporto_mobsf.json").read_text()))
    assert s["pacchetto"] == "com.luckymoon.casino"
    assert s["permessi_pericolosi"] == [
        "android.permission.ACCESS_FINE_LOCATION",
        "android.permission.READ_CONTACTS",
    ]
    assert "AppsFlyer" in s["librerie_pubblicitarie"] and "Google AdMob" in s["librerie_pubblicitarie"]
    assert s["domini_candidati"] == ["fastcashier.net", "luckymoon-casino.com"]
    assert s["certificato"]["sha256"] == "cd" * 32 and "Moon Gaming" in s["certificato"]["soggetto"]


def test_apk_upload_analysis_and_sites(db, store):
    sub = intake.submit_file(db, "casino.apk", b"PK\x03\x04 apk finto")
    job = db.query(Lavoro).filter(Lavoro.tipo == "apk").one()
    assert store.exists("betting-lavorazione", job.carico["chiave"])
    report = summarize(json.loads((F / "apk/rapporto_mobsf.json").read_text()))
    store.put(
        "prova-arrivo", f"{job.id}/manifesto.json", json.dumps({"esito": "riuscito", "apk": report}).encode()
    )
    out = apk.ingest_apk(db, job)
    assert out["siti_nuovi"] == 2
    assert {s.dominio for s in db.query(Sito)} == {"fastcashier.net", "luckymoon-casino.com"}
    assert {s.fonte_scoperta for s in db.query(Sito)} == {"apk"}
    assert (
        db.query(Estrazione).filter(Estrazione.tipo == "apk").one().metadati["pacchetto"]
        == "com.luckymoon.casino"
    )
    dyn = apk.request_apk_analysis(db, sub.media, dynamic=True)
    assert dyn.carico["pacchetto"] == "com.luckymoon.casino"


def test_flows_summary():
    lines = [
        json.dumps({"t": 10, "url": "https://ads.example-net.com/x", "byte": 100}),
        json.dumps({"t": 5, "url": "https://old.example.com/"}),
        "non json",
        json.dumps({"t": 11, "url": "https://ads.example-net.com/y", "byte": 50}),
    ]
    out = flows_summary(lines, since=9)
    assert out == {"richieste": 2, "domini": [{"host": "ads.example-net.com", "richieste": 2, "byte": 150}]}


def _site_with_company(db, domain, company, number=None):
    site = intake.get_or_create_site(db, domain)
    db.add(
        Indicatore(
            sito_id=site.id,
            codice="ragione_sociale_dichiarata",
            valore="presente",
            evidenza={"valore": company},
            certezza=0.8,
            collettore="dati_aziendali",
            versione_collettore="1",
        )
    )
    if number:
        db.add(
            Indicatore(
                sito_id=site.id,
                codice="partita_iva_dichiarata",
                valore="presente",
                evidenza={"valore": number},
                certezza=0.6,
                collettore="dati_aziendali",
                versione_collettore="1",
            )
        )
    db.flush()
    return site


REGISTRY = (
    b"nome;paese;numero;stato\nMoon Gaming N.V.;Curacao;154321;attiva\nSun Bet Ltd;Malta;C999;attiva\n;;;\n"
)


def test_legal_entity_candidates(db, store):
    n, errors = legal.load_registry(db, "societa", REGISTRY, "Registro di prova")
    assert n == 2 and errors == ["Riga 4: nome mancante"]
    assert legal.load_registry(db, "societa", REGISTRY, "x")[0] == 0  # stesso file: nessun doppione
    site = _site_with_company(db, "luckymoon.example.com", "MOON GAMING NV", "154321")
    best = legal.candidates(db, site)[0]
    assert best["nome"] == "Moon Gaming N.V." and best["paese"] == "Curacao" and best["punteggio"] > 0.7
    assert len(best["evidenze"]) == 3
    legal.confirm(db, site, best, None, accept=True)
    twin = intake.get_or_create_site(db, "sunnystar.example.org")
    db.add(
        LegameSito(
            sito_a=min(site.id, twin.id),
            sito_b=max(site.id, twin.id),
            motivo="tracciamento",
            valore="ga:G-1",
            forza=1,
        )
    )
    db.flush()
    assert legal.candidates(db, twin)[0]["nome"] == "Moon Gaming N.V."
    g = legal.graph(db, site)
    assert {n["tipo"] for n in g["nodi"]} >= {"sito", "legal_entity", "gemello"}
    assert all(0 <= n["x"] <= 100 for n in g["nodi"])


def test_no_candidate_from_weak_similarity(db):
    legal.load_registry(db, "societa", b"nome\nSun Gaming Ltd\n", "r")
    site = _site_with_company(db, "x.example.com", "Moon Gaming N.V.")
    assert [c["nome"] for c in legal.candidates(db, site)] == ["Moon Gaming N.V."]  # solo il dichiarato
    assert db.query(LegalEntity).count() == 0


def test_synthetic_anomalies():
    r = anomalies.run(400, 0.06, seed=3)
    assert r["dati"] == "sintetici"
    v = r["valutazione"]
    assert v["richiamo"] >= 0.8 and v["precisione"] >= 0.6
    assert all(s["motivi"] for s in r["segnalazioni"])
    assert all(s["conto"].startswith("SINT-") for s in r["segnalazioni"])


def test_event_rating():
    start = datetime(2026, 11, 20, 20, tzinfo=UTC)
    rows = []
    for book, home in [("A", 2.10), ("B", 2.05), ("C", 2.12), ("Compiacente", 1.60)]:
        for h in (30, 20, 10, 3):
            rows.append(
                {
                    "bookmaker": book,
                    "momento": start - timedelta(hours=h),
                    "esito": "1",
                    "quota": home if h > 6 else home * 0.8,
                    "volume": 100,
                }
            )
            rows.append(
                {
                    "bookmaker": book,
                    "momento": start - timedelta(hours=h),
                    "esito": "2",
                    "quota": 3.4,
                    "volume": 900 if h <= 6 else 50,
                }
            )
    out = events.rate(rows, start)
    kinds = {s["segnale"] for s in out["segnali"]}
    assert {"scostamento_bookmaker", "movimento_finale", "quota_volume"} <= kinds and out["rating"] == "alto"
    calm = [
        r | {"quota": 2.1} if r["esito"] == "1" else r | {"volume": 100}
        for r in rows
        if r["bookmaker"] != "Compiacente"
    ]
    assert events.rate(calm, start)["rating"] == "basso"


def test_event_csv():
    data = b"evento;inizio;bookmaker;momento;esito;quota;volume\nA-B;2026-11-20T20:00:00;Book1;2026-11-20T10:00:00;1;2,10;\nA-B;;Book1;x;1;0.5;\n"
    rows, errors = events.parse_csv(data)
    assert (
        len(rows) == 1
        and rows[0]["quota"] == 2.1
        and rows[0]["inizio"].tzinfo
        and errors == ["Riga 3: valori non leggibili"]
    )


def test_profiling_without_snapshots(db, store):
    assert profiling.profile_site(db, intake.get_or_create_site(db, "vuoto.example.com")) == {
        "saltato": "nessuno snapshot"
    }
