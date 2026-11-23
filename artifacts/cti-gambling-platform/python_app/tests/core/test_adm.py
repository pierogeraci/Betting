import pytest

from core import adm
from core.intake import get_or_create_site
from core.models import AdmCaricamento, Indicatore, Lavoro


def test_parse_inibiti(fixture_bytes):
    parsed = adm.parse_list(adm.INIBITI, fixture_bytes("adm/siti_inibiti.txt"))
    assert [r.domain for r in parsed.rows] == [
        "scommesse-finte.example.com",
        "casino-prova.net",
        "it.bet-esempio.org",
        "poker.rete-finta.co.uk",
    ]
    assert parsed.discarded == 2  # intestazione e riga senza dominio; il doppione non si ripete


@pytest.mark.parametrize("name", ["adm/concessionari.csv", "adm/concessionari.html"])
def test_parse_concessionari(fixture_bytes, name):
    parsed = adm.parse_list(adm.CONCESSIONARI, fixture_bytes(name))
    assert [(r.license_number, r.domain) for r in parsed.rows] == [
        ("15001", "giocolegale-prova.it"),
        ("15002", "scommesseregolari-prova.it"),
    ]
    assert parsed.rows[0].company == "Gioco Legale Prova S.p.A."


def test_unsupported_formats():
    with pytest.raises(adm.UnsupportedList):
        adm.parse_list(adm.INIBITI, b"%PDF-1.7 ...")
    with pytest.raises(adm.UnsupportedList):
        adm.parse_list(adm.INIBITI, b"PK\x03\x04...")


def test_not_loaded_is_not_determinable(db):
    results = adm.compare_hosts(db, ["qualsiasi.example.com"])
    assert {r.value for r in results.values()} == {"non_determinabile"}
    assert adm.summarize(results) == "non_determinabile"


def test_load_versions_and_compare(db, fixture_bytes):
    inibiti = fixture_bytes("adm/siti_inibiti.txt")
    load, created = adm.load_list(db, adm.INIBITI, inibiti, filename="inibiti.txt")
    assert created and load.versione == 1 and load.righe_valide == 4
    # Stesso file: nessuna nuova versione.
    again, created = adm.load_list(db, adm.INIBITI, inibiti, filename="inibiti.txt")
    assert not created and again.id == load.id
    adm.load_list(db, adm.CONCESSIONARI, fixture_bytes("adm/concessionari.csv"), filename="c.csv")

    exact = adm.compare_hosts(db, ["www.casino-prova.net"])
    assert exact[adm.INIBITI].value == "presente" and exact[adm.INIBITI].certainty == 1.0
    assert exact[adm.INIBITI].evidence["versione_elenco"] == 1
    assert exact[adm.CONCESSIONARI].value == "assente"
    assert adm.summarize(exact) == "inibito"

    # Sottodominio di un dominio in elenco: presente, con certezza minore.
    child = adm.compare_hosts(db, ["mobile.casino-prova.net"])[adm.INIBITI]
    assert child.value == "presente" and child.certainty == 0.9
    # In elenco c'è solo un sottodominio: corrispondenza debole.
    sibling = adm.compare_hosts(db, ["bet-esempio.org"])[adm.INIBITI]
    assert sibling.value == "presente" and sibling.certainty == 0.6

    legal = adm.compare_hosts(db, ["giocolegale-prova.it"])
    assert adm.summarize(legal) == "concessionario"
    assert legal[adm.CONCESSIONARI].evidence["numero_concessione"] == "15001"
    assert adm.summarize(adm.compare_hosts(db, ["neutro.example.org"])) == "non_in_elenco"

    # Una nuova versione sostituisce la precedente e chiede di riconfrontare i siti.
    new, created = adm.load_list(
        db, adm.INIBITI, inibiti + b"nuovo-inibito.example.net\n", filename="inibiti.txt"
    )
    assert created and new.versione == 2
    assert db.get(AdmCaricamento, load.id).stato == "sostituito"
    assert db.query(Lavoro).filter(Lavoro.tipo == "confronto_adm_tutti").count() == 3


def test_compare_site_writes_indicators(db, fixture_bytes):
    adm.load_list(db, adm.INIBITI, fixture_bytes("adm/siti_inibiti.txt"))
    site = get_or_create_site(db, "casino-prova.net")
    adm.compare_site(db, site)
    rows = {i.codice: i for i in db.query(Indicatore).filter(Indicatore.sito_id == site.id)}
    assert rows["dominio_inibito_adm"].valore == "presente"
    assert rows["dominio_inibito_adm"].evidenza["estratto"] == "casino-prova.net"
    # L'elenco dei concessionari non è caricato: non si può dire "assente".
    assert rows["dominio_concessionario_adm"].valore == "non_determinabile"
    assert site.esito_adm == "inibito"
