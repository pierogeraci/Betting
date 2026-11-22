"""Normalizzazione di URL e domini.

Il dominio registrabile (per esempio `esempio.co.uk`) identifica il sito; l'host
esatto resta nello snapshot. L'elenco dei suffissi è quello incluso in tldextract:
nessuna richiesta di rete.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import tldextract

_extract = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None, include_psl_private_domains=False)

_HOST_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9_]([a-z0-9_-]{0,61}[a-z0-9_])?\.)+[a-z0-9-]{2,63}$")
_ONION_RE = re.compile(r"^([a-z0-9-]+\.)*[a-z2-7]{16}([a-z2-7]{40})?\.onion$")


class InvalidUrl(ValueError):
    """URL che non si può accettare. Il messaggio è per l'analista."""


@dataclass(frozen=True)
class NormalizedUrl:
    url: str
    host: str
    registrable: str
    is_onion: bool
    scheme_assumed: bool


def normalize_host(raw: str) -> str:
    """Host in minuscolo, in punycode, senza punto finale. Solleva InvalidUrl."""
    host = raw.strip().strip(".").lower()
    if not host:
        raise InvalidUrl("Manca il nome del sito.")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise InvalidUrl(f"Nome del sito non valido: {raw!r}.") from exc
    if not _HOST_RE.match(host):
        raise InvalidUrl(f"Nome del sito non valido: {raw!r}.")
    return host


def registrable_domain(host: str) -> str:
    """Dominio registrabile dell'host; per i .onion e i suffissi sconosciuti resta l'host."""
    if host.endswith(".onion"):
        return host.split(".")[-2] + ".onion"
    parts = _extract(host)
    if parts.domain and parts.suffix:
        return f"{parts.domain}.{parts.suffix}"
    return host


def strip_www(host: str) -> str:
    return host[4:] if host.startswith("www.") else host


def parent_domains(host: str) -> list[str]:
    """L'host e i suoi domini padre fino al dominio registrabile, dal più specifico."""
    base = registrable_domain(host)
    out = [host]
    current = host
    while current != base and "." in current:
        current = current.split(".", 1)[1]
        out.append(current)
        if len(out) > 10:
            break
    if base not in out:
        out.append(base)
    return out


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


def normalize_url(raw: str) -> NormalizedUrl:
    """Valida e normalizza un URL inserito a mano.

    Si accettano solo http e https verso un nome di dominio pubblico. Indirizzi IP,
    nomi interni e credenziali nell'URL sono rifiutati: il contenitore di raccolta
    non deve poter essere puntato verso servizi interni.
    """
    text = (raw or "").strip()
    if not text:
        raise InvalidUrl("URL vuoto.")
    if len(text) > 2000:
        raise InvalidUrl("URL troppo lungo.")
    if any(ch.isspace() for ch in text):
        raise InvalidUrl("L'URL contiene spazi.")
    scheme_assumed = False
    if "://" not in text:
        text = "https://" + text
        scheme_assumed = True
    parts = urlsplit(text)
    if parts.scheme.lower() not in {"http", "https"}:
        raise InvalidUrl("Sono ammessi solo indirizzi http e https.")
    if parts.username or parts.password:
        raise InvalidUrl("L'URL non può contenere credenziali.")
    raw_host = parts.hostname or ""
    if _is_ip(raw_host):
        raise InvalidUrl("Serve un nome di dominio, non un indirizzo IP.")
    host = normalize_host(raw_host)
    is_onion = host.endswith(".onion")
    if is_onion and not _ONION_RE.match(host):
        raise InvalidUrl("Indirizzo .onion non valido.")
    if not is_onion and not _extract(host).suffix:
        raise InvalidUrl("Il dominio non ha un suffisso pubblico riconosciuto.")
    try:
        port = parts.port
    except ValueError as exc:
        raise InvalidUrl("Porta non valida.") from exc
    default_port = {"http": 80, "https": 443}[parts.scheme.lower()]
    netloc = host if port in (None, default_port) else f"{host}:{port}"
    path = parts.path or "/"
    url = urlunsplit((parts.scheme.lower(), netloc, path, parts.query, ""))
    return NormalizedUrl(
        url=url,
        host=host,
        registrable=registrable_domain(host),
        is_onion=is_onion,
        scheme_assumed=scheme_assumed,
    )


_DOMAIN_TOKEN = re.compile(r"(?i)\b((?:[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9_])?\.)+[a-z][a-z0-9-]{1,62})\b")


def find_domain(text: str) -> str | None:
    """Primo nome di dominio valido in una riga di testo, normalizzato; None se non c'è."""
    candidate = text.strip()
    if "://" in candidate:
        candidate = urlsplit(candidate.split()[0]).hostname or candidate
    for match in _DOMAIN_TOKEN.finditer(candidate):
        try:
            host = normalize_host(match.group(1))
        except InvalidUrl:
            continue
        if host.endswith(".onion") or _extract(host).suffix:
            return host
    return None
