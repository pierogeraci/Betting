"""Base comune dei collettori.

Un collettore riceve le pagine già archiviate di un sito (una o più viste di
snapshot) e restituisce indicatori. Non fa richieste di rete e non decide il rischio.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import cached_property
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

PRESENTE, ASSENTE, ND = "presente", "assente", "non_determinabile"
# Sotto questa quantità di testo visibile una pagina non basta per dire "assente".
MIN_TEXT = 400


@dataclass
class Indicator:
    code: str
    value: str
    certainty: float
    collector: str
    version: str
    evidence: dict[str, Any] = field(default_factory=dict)
    area: str = ""

    def as_row(self) -> dict[str, Any]:
        return {
            "codice": self.code,
            "valore": self.value,
            "certezza": round(self.certainty, 3),
            "collettore": self.collector,
            "versione_collettore": self.version,
            "evidenza": self.evidence,
        }


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.images: list[tuple[str, str]] = []
        self.scripts: list[str] = []
        self.inline_scripts: list[str] = []
        self.forms: list[dict[str, Any]] = []
        self.tags: list[str] = []
        self.icons: list[str] = []
        self.text: list[str] = []
        self.footer_depth = 0
        self.footer: list[str] = []
        self._skip = 0
        self._a: tuple[str, list[str]] | None = None
        self._script: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        self.tags.append(tag)
        if tag in {"script", "style", "noscript", "template"}:
            self._skip += 1
            if tag == "script":
                if a.get("src"):
                    self.scripts.append(a["src"])
                else:
                    self._script = []
        elif tag == "a":
            self._a = (a.get("href", ""), [])
        elif tag == "img":
            self.images.append(
                (a.get("src", "") or a.get("data-src", ""), " ".join([a.get("alt", ""), a.get("title", "")]))
            )
        elif tag == "link" and "icon" in a.get("rel", "").lower():
            self.icons.append(a.get("href", ""))
        elif tag == "form":
            self.forms.append({"action": a.get("action", ""), "inputs": []})
        elif tag == "input" and self.forms:
            self.forms[-1]["inputs"].append((a.get("type", "text"), a.get("name", "")))
        if tag == "footer" or "footer" in a.get("class", "").lower() or "footer" in a.get("id", "").lower():
            self.footer_depth += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "template"} and self._skip:
            self._skip -= 1
            if tag == "script" and self._script is not None:
                self.inline_scripts.append("".join(self._script))
                self._script = None
        elif tag == "a" and self._a is not None:
            self.links.append((self._a[0], " ".join("".join(self._a[1]).split())))
            self._a = None
        elif tag == "footer" and self.footer_depth:
            self.footer_depth -= 1

    def handle_data(self, data):
        if self._script is not None:
            self._script.append(data)
        if self._skip:
            return
        self.text.append(data)
        if self._a is not None:
            self._a[1].append(data)
        if self.footer_depth:
            self.footer.append(data)


@dataclass
class Page:
    """Una pagina archiviata, pronta per i collettori."""

    url: str
    html: str
    snapshot_id: int | None = None
    status: str = "riuscito"
    traffic_hosts: list[str] = field(default_factory=list)
    title: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @cached_property
    def parsed(self) -> _Parser:
        parser = _Parser()
        try:
            parser.feed(self.html or "")
            parser.close()
        except Exception:  # noqa: BLE001, S110 - HTML ostile o malformato: si usa quel che si è letto
            pass
        return parser

    @cached_property
    def text(self) -> str:
        return " ".join(" ".join(self.parsed.text).split())

    @cached_property
    def text_norm(self) -> str:
        return normalize(self.text)

    @cached_property
    def footer_text(self) -> str:
        return " ".join(" ".join(self.parsed.footer).split())

    @property
    def readable(self) -> bool:
        return self.status == "riuscito" and len(self.text) >= MIN_TEXT

    @cached_property
    def host(self) -> str:
        return (urlsplit(self.url).hostname or "").lower()

    def absolute(self, href: str) -> str:
        return urljoin(self.url, href)

    @cached_property
    def links(self) -> list[tuple[str, str]]:
        out = []
        for href, label in self.parsed.links:
            if href and not href.startswith(("javascript:", "mailto:", "tel:", "#")):
                out.append((self.absolute(href), label))
        return out

    @cached_property
    def all_hosts(self) -> list[str]:
        hosts = set(self.traffic_hosts)
        for src in self.parsed.scripts + [i[0] for i in self.parsed.images]:
            h = urlsplit(self.absolute(src)).hostname
            if h:
                hosts.add(h.lower())
        return sorted(hosts)


def normalize(text: str) -> str:
    """Minuscolo, senza accenti, spazi compattati: per confronti con elenchi di termini."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.lower().split())


def excerpt(text: str, start: int, end: int, width: int = 90) -> str:
    a, b = max(0, start - width), min(len(text), end + width)
    return ("…" if a else "") + text[a:b].strip() + ("…" if b < len(text) else "")


def find_terms(page: Page, terms: list[str]) -> tuple[str, str] | None:
    """Primo termine trovato nel testo visibile normalizzato: (termine, estratto)."""
    text = page.text_norm
    for term in terms:
        pattern = r"(?<![a-z0-9])" + re.escape(normalize(term)) + r"(?![a-z0-9])"
        match = re.search(pattern, text)
        if match:
            return term, excerpt(text, match.start(), match.end())
    return None


def find_regex(page: Page, pattern: str, flags: int = re.I, source: str = "text") -> re.Match[str] | None:
    haystack = page.text if source == "text" else page.html
    return re.search(pattern, haystack or "", flags)


def evidence(page: Page, quote: str, **extra: Any) -> dict[str, Any]:
    return {"url": page.url, "snapshot_id": page.snapshot_id, "estratto": quote[:400]} | extra


def any_readable(pages: list[Page]) -> bool:
    return any(p.readable for p in pages)
