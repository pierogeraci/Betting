import pytest

from core.domains import InvalidUrl, find_domain, normalize_url, parent_domains, registrable_domain


def test_normalize_adds_scheme_and_lowercases():
    url = normalize_url("WWW.Esempio.CO.UK/Pagina?a=1#frammento")
    assert url.url == "https://www.esempio.co.uk/Pagina?a=1"
    assert url.registrable == "esempio.co.uk"
    assert url.scheme_assumed


def test_normalize_idn_to_punycode():
    assert normalize_url("http://scommésse.example.com").host == "xn--scommsse-f1a.example.com"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://db:5432/",
        "localhost",
        "ftp://a.example.com",
        "http://utente:segreto@a.example.com",
        "javascript:alert(1)",
        "http://a b.com",
        "http://169.254.169.254/latest",
    ],
)
def test_normalize_rejects_internal_and_unsafe(raw):
    with pytest.raises(InvalidUrl):
        normalize_url(raw)


def test_onion():
    host = "a" * 56 + ".onion"
    url = normalize_url(f"http://{host}/")
    assert url.is_onion and url.registrable == host
    with pytest.raises(InvalidUrl):
        normalize_url("http://corto.onion/")


def test_parent_domains_and_registrable():
    assert parent_domains("a.b.esempio.co.uk") == ["a.b.esempio.co.uk", "b.esempio.co.uk", "esempio.co.uk"]
    assert registrable_domain("www.sito.it") == "sito.it"


def test_find_domain_in_line():
    assert find_domain("12;https://www.bet-xyz.com/it;2020") == "www.bet-xyz.com"
    assert find_domain("riga senza dominio") is None
