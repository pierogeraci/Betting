"""Per ogni indicatore delle vulnerabilità: un caso presente, uno assente, uno non determinabile."""

from pathlib import Path

import pytest

from collectors import aziendali, identificazione, infrastruttura, offerta, pagamenti, titolo
from collectors.base import Page

F = Path(__file__).resolve().parent.parent / "fixtures" / "snapshots"


def page(name, url, status="riuscito", hosts=()):
    return Page(
        url=url,
        html=(F / name).read_text(encoding="utf-8"),
        snapshot_id=1,
        status=status,
        traffic_hosts=list(hosts),
    )


CRYPTO = [
    page("crypto_home.html", "https://www.luckymoon.example.com/", hosts=["embed.tawk.to", "www.skrill.com"]),
    page("crypto_terms.html", "https://www.luckymoon.example.com/terms-and-conditions"),
]
LEGALE = [
    page("legale_home.html", "https://www.giocolegale-prova.it/"),
    page("legale_pagamenti.html", "https://www.giocolegale-prova.it/metodi-di-pagamento"),
]
OFFSHORE = [page("offshore_pagamenti.html", "https://offshore.example.org/payments")]
BLOCCATO = [
    Page(url="https://x.example.com/", html="<html><title>Just a moment</title></html>", status="bloccato")
]


def values(collector, pages):
    return {i.code: i for i in collector.collect(pages)}


@pytest.mark.parametrize(
    ("pages", "expected"),
    [
        (
            CRYPTO,
            {
                "pagamento_criptovalute": "presente",
                "pagamento_terze_parti": "presente",
                "pagamento_conto_ue": "non_determinabile",
            },
        ),
        (
            LEGALE,
            {
                "pagamento_criptovalute": "assente",
                "pagamento_terze_parti": "assente",
                "pagamento_conto_ue": "presente",
            },
        ),
        (OFFSHORE, {"pagamento_offshore": "presente", "pagamento_criptovalute": "assente"}),
        (
            BLOCCATO,
            {
                "pagamento_criptovalute": "non_determinabile",
                "pagamento_offshore": "non_determinabile",
                "pagamento_terze_parti": "non_determinabile",
                "pagamento_conto_ue": "non_determinabile",
            },
        ),
    ],
)
def test_pagamenti(pages, expected):
    got = values(pagamenti, pages)
    for code, value in expected.items():
        assert got[code].value == value, code
        if value == "presente":
            assert got[code].evidence["estratto"] and got[code].evidence["url"]


def test_crypto_wallet_is_evidence():
    ind = values(pagamenti, CRYPTO)["pagamento_criptovalute"]
    assert "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq" in ind.evidence["estratto"]


def test_offshore_never_absent_without_deposit_data():
    assert values(pagamenti, LEGALE)["pagamento_offshore"].value == "non_determinabile"


@pytest.mark.parametrize(
    ("pages", "expected"),
    [
        (
            CRYPTO,
            {
                "assenza_documento": "presente",
                "piu_account_per_conto": "presente",
                "assenza_registrazione": "assente",
            },
        ),
        (
            LEGALE,
            {
                "assenza_documento": "assente",
                "piu_account_per_conto": "assente",
                "assenza_registrazione": "assente",
            },
        ),
        (
            BLOCCATO,
            {
                "assenza_documento": "non_determinabile",
                "piu_account_per_conto": "non_determinabile",
                "assenza_registrazione": "non_determinabile",
            },
        ),
    ],
)
def test_identificazione(pages, expected):
    got = values(identificazione, pages)
    for code, value in expected.items():
        assert got[code].value == value, code


def test_no_registration_present():
    p = Page(
        url="https://n.example.com/",
        html="<html><body><p>"
        + "Gioca subito senza registrazione, nessun account. " * 20
        + "</p></body></html>",
    )
    assert values(identificazione, [p])["assenza_registrazione"].value == "presente"


def test_titolo():
    legal = values(titolo, LEGALE)
    assert legal["logo_adm_esposto"].value == "presente"
    assert legal["numero_concessione_dichiarato"].evidence["numero"] == "15001"
    crypto = values(titolo, CRYPTO)
    assert crypto["logo_adm_esposto"].value == "assente"
    assert "Curaçao" in crypto["licenza_estera_dichiarata"].evidence["licenze"]
    assert values(titolo, BLOCCATO)["logo_adm_esposto"].value == "non_determinabile"


def test_aziendali():
    legal = values(aziendali, LEGALE)
    assert legal["ragione_sociale_dichiarata"].evidence["valore"].startswith("Gioco Legale Prova S.p.A")
    assert legal["partita_iva_dichiarata"].evidence["valore"] == "01234567897"
    crypto = values(aziendali, CRYPTO)
    assert "Moon Gaming N.V." in crypto["ragione_sociale_dichiarata"].evidence["valore"]
    assert crypto["partita_iva_dichiarata"].evidence.get("tipo") == "numero di registrazione estero"
    assert "Cura" in crypto["sede_dichiarata"].evidence["valore"]


def test_offerta():
    got = values(offerta, CRYPTO)
    tipi = got["tipi_gioco"].evidence["tipi"]
    assert {"slot", "casino_live", "crypto_games", "scommesse_sportive"} <= set(tipi)
    assert tipi["slot"]["criteri"]["natura_rischio"] == "azzardo"
    assert got["quote_visibili"].value == "presente"
    assert got["chat_dal_vivo"].evidence["servizi"] == ["Tawk.to"]
    assert got["immagini_esterne"].evidence["servizi"] == ["Cloudinary"]
    assert got["link_pagamento_rapido"].evidence["link"][0]["dominio"] == "example.net"
    assert got["lingua_italiana"].value == "assente"
    assert values(offerta, LEGALE)["lingua_italiana"].value == "presente"


def test_infrastruttura():
    got = values(infrastruttura, CRYPTO)
    ids = got["identificativi_tracciamento"].evidence["identificativi"]
    assert ids["google_analytics"] == ["G-ABC123XYZ9"] and ids["facebook_pixel"] == ["123456789012345"]
    assert "skrill.com" in got["domini_terze_parti"].evidence["domini"]
    assert got["dati_rete"].value == "non_determinabile"


def test_simhash_same_template():
    a = Page(url="https://a.example.com/", html=(F / "crypto_home.html").read_text())
    b = Page(
        url="https://b.example.com/",
        html=(F / "crypto_home.html").read_text().replace("LuckyMoon", "SunnyStar"),
    )
    c = Page(url="https://c.example.com/", html=(F / "legale_home.html").read_text())
    fa, fb, fc = (infrastruttura.structure_fingerprint(p) for p in (a, b, c))
    assert infrastruttura.simhash_distance(fa, fb) <= 3 < infrastruttura.simhash_distance(fa, fc)
