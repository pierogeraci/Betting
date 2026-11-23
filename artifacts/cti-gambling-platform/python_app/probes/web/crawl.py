"""Crawler di scoperta per pagine web e .onion, eseguito in un processo a sé.

Uso: python -m probes.web.crawl <carico.json> <risultato.json>

Scrapy gestisce code, deduplica, rispetto di robots.txt e limitazione di velocità.
Le pagine .onion passano dal proxy SOCKS del contenitore Tor tramite Playwright.
Nessun modulo compilato, nessun accesso, nessun nuovo tentativo su una pagina bloccata.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any
from urllib.parse import urlsplit

USER_AGENT = "betting-antifrode/0.1 (+ricerca su pagine pubbliche)"
MAX_DEPTH = 2
MAX_PAGES = 200


def abort_browser_request(request) -> bool:
    """Nel browser usato per Tor ogni richiesta passa di qui: solo .onion, mai indirizzi interni, niente media."""
    from probes.snapshot.guard import url_allowed

    if request.resource_type in {"image", "media", "font"}:
        return True
    host = (urlsplit(request.url).hostname or "").lower()
    if request.url.startswith(("data:", "blob:")):
        return False
    return not host.endswith(".onion") or not url_allowed(request.url)


def settings(payload: dict[str, Any]) -> dict[str, Any]:
    tor = bool(payload.get("tor"))
    base = {
        "USER_AGENT": USER_AGENT,
        "ROBOTSTXT_OBEY": True,
        "DOWNLOAD_DELAY": 2.0,
        "RANDOMIZE_DOWNLOAD_DELAY": False,
        "CONCURRENT_REQUESTS": 4,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 2.0,
        "RETRY_ENABLED": False,
        "COOKIES_ENABLED": False,
        # Tetti applicati anche qui, non solo nel pianificatore e nel portale.
        "DEPTH_LIMIT": max(0, min(int(payload.get("profondita", 1)), MAX_DEPTH)),
        "CLOSESPIDER_PAGECOUNT": max(1, min(int(payload.get("max_pagine", 40)), MAX_PAGES)),
        "CLOSESPIDER_TIMEOUT": 1800,
        "DOWNLOAD_TIMEOUT": 60,
        "DOWNLOAD_MAXSIZE": 5_000_000,
        "HTTPERROR_ALLOW_ALL": True,
        "LOG_LEVEL": "WARNING",
        "TELNETCONSOLE_ENABLED": False,
        "DOWNLOADER_MIDDLEWARES": {"probes.web.crawl.GuardMiddleware": 50},
    }
    if tor:
        base |= {
            "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
            "DOWNLOAD_HANDLERS": {
                "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
                "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
            },
            "PLAYWRIGHT_LAUNCH_OPTIONS": {
                "headless": True,
                "proxy": {
                    "server": os.environ.get("TOR_SOCKS_URL", "socks5://tor:9050").replace(
                        "socks5h", "socks5"
                    )
                },
            },
            "PLAYWRIGHT_ABORT_REQUEST": abort_browser_request,
            "DOWNLOAD_TIMEOUT": 120,
        }
    return base


class GuardMiddleware:
    """Scarta le richieste verso indirizzi non pubblici e, per Tor, fuori dalla rete .onion."""

    def __init__(self, tor: bool = False) -> None:
        self.tor = tor

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            tor=crawler.settings.get("DOWNLOAD_HANDLERS", {}).get("http", "").startswith("scrapy_playwright")
        )

    def process_request(self, request, spider=None):
        from scrapy.exceptions import IgnoreRequest

        from probes.snapshot.guard import url_allowed

        host = (urlsplit(request.url).hostname or "").lower()
        if self.tor and not host.endswith(".onion"):
            raise IgnoreRequest("fuori dalla rete Tor")
        if not url_allowed(request.url):
            raise IgnoreRequest("indirizzo non pubblico")
        return None


def run(payload: dict[str, Any]) -> dict[str, Any]:
    import scrapy
    from scrapy.crawler import CrawlerProcess

    from probes.web.parse import parse_page

    pages: list[dict[str, Any]] = []
    words = payload.get("parole", [])
    tor = bool(payload.get("tor"))

    class DiscoverySpider(scrapy.Spider):
        name = "scoperta"
        start_urls = payload.get("semi", [])

        def start_requests(self):
            for url in self.start_urls:
                yield scrapy.Request(url, meta={"playwright": tor}, dont_filter=False)

        def parse(self, response):
            content_type = response.headers.get("Content-Type", b"").decode("latin-1").lower()
            if "html" not in content_type and not tor:
                return
            item = parse_page(response.url, response.status, response.text, words)
            pages.append(item)
            if item["bloccato"] or response.status >= 400:
                return  # una pagina bloccata non si esplora e non si ritenta
            for link in item["link_interni"]:
                yield scrapy.Request(link, meta={"playwright": tor}, callback=self.parse)

    process = CrawlerProcess(settings=settings(payload))
    process.crawl(DiscoverySpider)
    process.start()
    return {"pagine": pages, "tor": tor}


def main() -> None:
    payload = json.loads(open(sys.argv[1], encoding="utf-8").read())  # noqa: PTH123
    result = run(payload)
    with open(sys.argv[2], "w", encoding="utf-8") as handle:  # noqa: PTH123
        json.dump(result, handle)


if __name__ == "__main__":
    main()
