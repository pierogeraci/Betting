import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from collectors.base import Page
from core import adm, ingest, intake, profiling
from core.bets import observed_bets, parse_amount, parse_upload
from core.models import Lavoro, LegameSito, Puntata, Punteggio, Revisione
from core.storage import sha256_hex

F = Path(__file__).resolve().parent.parent / "fixtures" / "snapshots"


def drop_snapshot(db, store, url, fixture, secondary=False, hosts=(), html=None):
    site = intake.get_or_create_site(db, intake.normalize_url(url).registrable)
    job = intake.request_snapshot(db, site, url, secondary=secondary)
    html = html if html is not None else (F / fixture).read_bytes()
    har = json.dumps(
        {
            "log": {
                "entries": [
                    {"request": {"url": f"https://{h}/x.js"}, "response": {"status": 200}} for h in hosts
                ]
            }
        }
    ).encode()
    files = {"pagina.html": html, "traffico.har": har}
    manifest = {
        "esito": "riuscito",
        "url_finale": url,
        "codice_http": 200,
        "raccolto_il": datetime.now(UTC).isoformat(),
        "file": {
            "html": {"nome": "pagina.html", "sha256": sha256_hex(html)},
            "traffico": {"nome": "traffico.har", "sha256": sha256_hex(har)},
        },
    }
    for n, d in files.items():
        store.put("prova-arrivo", f"{job.id}/{n}", d)
    store.put("prova-arrivo", f"{job.id}/manifesto.json", json.dumps(manifest).encode())
    return site, ingest.ingest_snapshot(db, job)


def test_home_requests_secondary_pages_and_profile(db, store):
    site, snap = drop_snapshot(db, store, "https://www.luckymoon.example.com/", "crypto_home.html")
    urls = {
        j.carico["url"]
        for j in db.query(Lavoro).filter(
            Lavoro.tipo == "snapshot", Lavoro.carico["secondaria"].astext == "true"
        )
    }
    assert urls == {
        "https://www.luckymoon.example.com/signup",
        "https://www.luckymoon.example.com/terms-and-conditions",
        "https://www.luckymoon.example.com/payments",
    }
    assert db.query(Lavoro).filter(Lavoro.tipo == "profila").count() == 1
    assert db.query(Lavoro).filter(Lavoro.tipo == "rete", Lavoro.coda == "raccolta").count() == 1
    # Una pagina secondaria non ne chiede altre e non rifà il confronto ADM.
    drop_snapshot(
        db,
        store,
        "https://www.luckymoon.example.com/terms-and-conditions",
        "crypto_terms.html",
        secondary=True,
    )
    assert (
        db.query(Lavoro).filter(Lavoro.tipo == "snapshot").count() == 5
    )  # 1 home, 3 secondarie, 1 della prova
    assert db.query(Lavoro).filter(Lavoro.tipo == "profila").count() == 1  # già in coda: nessun doppione


def test_profile_scores_and_flags(db, store):
    adm.load_list(db, adm.CONCESSIONARI, b"15009;Altro S.p.A.;www.altro-concessionario.it\n")
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
    result = profiling.profile_site(db, site)
    assert result["pagine"] == 2 and result["indicatori"] > 20
    inds = profiling.latest_indicators(db, site.id)
    assert (
        inds["pagamento_criptovalute"].valore == "presente"
        and inds["piu_account_per_conto"].valore == "presente"
    )
    score = db.query(Punteggio).filter(Punteggio.sito_id == site.id).one()
    assert score.versione_regole == "dossier-0.5.1" and score.trust_index is None
    assert "puntata" in score.dettaglio["esclusione"]
    assert (
        score.dettaglio["vulnerabilita"]["punteggio"] >= 12.5
    )  # cripto 6 + documento 3 + terzi 2 + account 1.5
    # Puntate caricate: ora l'indice si emette.
    start = datetime(2026, 11, 1, tzinfo=UTC)
    for i, (s, w) in enumerate([(3, 24), (1000, 2), (5, 0), (100, 59), (10, 67)]):
        db.add(
            Puntata(
                sito_id=site.id,
                importo_puntato=s,
                importo_vinto=w,
                valuta="EUR",
                momento=start + timedelta(minutes=i),
                fonte="caricata",
                tipo_gioco="slot" if i % 2 else None,
            )
        )
    db.flush()
    rows = profiling.score_site(db, site)
    platform = rows[0]
    assert platform.minaccia == 6 and platform.trust_index is not None and platform.classe_rischio == "alto"
    assert {r.ambito for r in rows} == {"piattaforma", "gioco:slot"}
    assert db.query(Punteggio).filter(Punteggio.sito_id == site.id).count() == 3  # lo storico resta


def test_adm_without_title_flag(db, store):
    adm.load_list(db, adm.CONCESSIONARI, b"15009;Altro S.p.A.;www.altro-concessionario.it\n")
    site, _ = drop_snapshot(db, store, "https://www.falso-legale.example.com/", "legale_home.html")
    profiling.profile_site(db, site)
    review = (
        db.query(Revisione).filter(Revisione.sito_id == site.id, Revisione.tipo == "adm_senza_titolo").one()
    )
    assert "segnalazione immediata" in review.motivo
    assert db.query(Punteggio).filter(Punteggio.sito_id == site.id).one().dettaglio["segnalazioni"] == [
        "adm_senza_titolo"
    ]


def test_licensee_is_excluded(db, store):
    adm.load_list(
        db,
        adm.CONCESSIONARI,
        (Path(__file__).resolve().parent.parent / "fixtures/adm/concessionari.csv").read_bytes(),
    )
    site, _ = drop_snapshot(db, store, "https://www.giocolegale-prova.it/", "legale_home.html")
    assert site.esito_adm == "concessionario"
    profiling.profile_site(db, site)
    score = db.query(Punteggio).filter(Punteggio.sito_id == site.id).one()
    assert "Concessionario" in score.dettaglio["esclusione"]
    assert not db.query(Revisione).filter(Revisione.tipo == "adm_senza_titolo").count()


def test_twins_by_tracking_id(db, store):
    a, _ = drop_snapshot(db, store, "https://www.luckymoon.example.com/", "crypto_home.html")
    profiling.profile_site(db, a)
    html = (F / "crypto_home.html").read_text().replace("LuckyMoon", "SunnyStar").encode()
    b, _ = drop_snapshot(db, store, "https://sunnystar-bet.example.org/", None, html=html)
    profiling.profile_site(db, b)
    reasons = {(row.motivo, row.valore) for row in db.query(LegameSito)}
    assert ("tracciamento", "google_analytics:G-ABC123XYZ9") in reasons
    assert "struttura_html" in {r for r, _ in reasons}
    db.refresh(a), db.refresh(b)
    assert a.gruppo == b.gruppo == min(a.id, b.id)
    assert profiling.twins_of(db, a.id)[0]["sito"].id == b.id


def test_entities_from_profile(db, store):
    from core.models import Entita

    site, _ = drop_snapshot(db, store, "https://www.luckymoon.example.com/", "crypto_home.html")
    profiling.profile_site(db, site)
    kinds = {(e.tipo, e.valore) for e in db.query(Entita)}
    assert ("portafoglio_btc", "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq") in kinds
    assert ("tracciamento", "facebook_pixel:123456789012345") in kinds
    assert ("licenza", "Curaçao") in kinds


def test_parse_amounts():
    assert parse_amount("€ 1.234,50") == (1234.5, "EUR")
    assert parse_amount("12.50 USD") == (12.5, "USD")
    assert parse_amount("0.0021 BTC") == (0.0021, "BTC")
    assert parse_amount("1,000") == (1000.0, "EUR")


def test_observed_bets_ignore_players():
    html = """<table><tr><th>Utente</th><th>Gioco</th><th>Puntata</th><th>Vincita</th></tr>
    <tr><td>mar***</td><td>Crash</td><td>€ 10,00</td><td>€ 25,00</td></tr>
    <tr><td>lu***</td><td>Dice</td><td>€ 5,00</td><td>-</td></tr>
    <tr><td>an***</td><td>Crash</td><td>€ 300,00</td><td>€ 0,00</td></tr></table>"""
    rows = observed_bets(Page(url="https://x.example.com/", html=html))
    assert [(r.stake, r.won, r.game) for r in rows] == [(10, 25, "Crash"), (5, 0, "Dice"), (300, 0, "Crash")]
    assert not any("mar" in str(vars(r)) for r in rows)


def test_parse_upload():
    rows, errors = parse_upload(
        b"importo_puntato;importo_vinto;valuta;momento;tipo_gioco\n10;0;EUR;2026-11-01T10:00:00;slot\n5,5;12;USD;;\nx;1;;;\n"
    )
    assert [(r.stake, r.won, r.currency) for r in rows] == [(10, 0, "EUR"), (5.5, 12, "USD")]
    assert rows[0].at.tzinfo is not None and errors == ["Riga 4: importo puntato non leggibile"]
