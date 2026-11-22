from probes.web.crawl import GuardMiddleware, settings
from probes.web.parse import parse_page

HTML = """<html><head><title>Directory casinò</title></head><body>
<p>Elenco di casino e scommesse senza documenti.</p>
<a href="/pagina-2">Avanti</a> <a href="https://nuovo-casino.example.net/?ref=1#x">Nuovo casino</a>
<a href="mailto:a@b.c">Mail</a> <a href="javascript:void(0)">x</a>
</body></html>"""


def test_parse_page_links_and_keywords():
    out = parse_page("https://dir.example.org/lista", 200, HTML, ["casino", "senza documenti", "poker"])
    assert out["titolo"] == "Directory casinò"
    assert out["link_interni"] == ["https://dir.example.org/pagina-2"]
    assert out["link_esterni"] == ["https://nuovo-casino.example.net/?ref=1"]
    assert out["parole"] == ["casino", "senza documenti"] and out["bloccato"] is None


def test_blocked_page_is_marked():
    assert (
        parse_page("https://x.example.org/", 403, "<title>Just a moment...</title>", [])["bloccato"]
        == "verifica_antibot"
    )


def test_settings_are_polite():
    s = settings({"profondita": 5, "max_pagine": 10})
    assert s["ROBOTSTXT_OBEY"] and not s["RETRY_ENABLED"] and s["CONCURRENT_REQUESTS_PER_DOMAIN"] == 1
    assert s["DOWNLOAD_DELAY"] >= 2 and s["CLOSESPIDER_PAGECOUNT"] == 10
    assert "PLAYWRIGHT_LAUNCH_OPTIONS" not in s
    tor = settings({"tor": True})
    assert tor["PLAYWRIGHT_LAUNCH_OPTIONS"]["proxy"]["server"].startswith("socks5://")


def test_guard_middleware():
    import pytest
    from scrapy import Request
    from scrapy.exceptions import IgnoreRequest

    plain, tor = GuardMiddleware(), GuardMiddleware(tor=True)
    assert plain.process_request(Request("https://93.184.216.34/")) is None
    for mw, url in [
        (plain, "http://127.0.0.1/"),
        (plain, "http://10.1.2.3/"),
        (tor, "https://clearweb.example.com/"),
    ]:
        with pytest.raises(IgnoreRequest):
            mw.process_request(Request(url))
    assert tor.process_request(Request("http://" + "a" * 56 + ".onion/")) is None
