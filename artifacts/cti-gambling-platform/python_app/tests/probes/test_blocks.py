import pytest

from probes.snapshot.blocks import detect_block
from probes.snapshot.guard import url_allowed


@pytest.mark.parametrize(
    ("name", "status", "reason"),
    [
        ("cloudflare.html", 403, "verifica_antibot"),
        ("cloudflare.html", 200, "verifica_antibot"),
        ("captcha.html", 200, "captcha"),
        ("geo.html", 200, "blocco_geografico"),
    ],
)
def test_block_pages(fixture_bytes, name, status, reason):
    verdict = detect_block(status, fixture_bytes(f"blocchi/{name}").decode())
    assert verdict.blocked and verdict.reason == reason and verdict.excerpt


def test_normal_page_with_captcha_in_form_is_not_blocked(fixture_bytes):
    assert not detect_block(200, fixture_bytes("blocchi/pagina_normale.html").decode()).blocked


@pytest.mark.parametrize(
    ("status", "reason"), [(403, "accesso_negato"), (429, "limite_richieste"), (451, "blocco_legale")]
)
def test_status_codes(status, reason):
    assert detect_block(status, "<html><body>no</body></html>").reason == reason


def test_guard_blocks_internal_addresses():
    for url in [
        "http://127.0.0.1:5432/",
        "http://localhost/",
        "http://10.0.0.5/",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/",
        "http://db/",
        "file:///etc/passwd",
        "http://192.168.1.1/",
    ]:
        assert not url_allowed(url), url
    assert url_allowed("https://93.184.216.34/")
    assert url_allowed("data:text/plain,ciao")
