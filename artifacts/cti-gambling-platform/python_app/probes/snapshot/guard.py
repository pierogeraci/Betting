"""Impedisce al browser di raccolta di raggiungere indirizzi interni.

Una pagina ostile può chiedere al browser di contattare servizi della rete locale
(database, archivio, metadati del cloud). Ogni richiesta verso un indirizzo non
pubblico viene interrotta.
"""

from __future__ import annotations

import ipaddress
import socket
from functools import lru_cache
from urllib.parse import urlsplit


def _public_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return ip.is_global and not ip.is_multicast


@lru_cache(maxsize=2048)
def host_is_public(host: str) -> bool:
    host = host.strip("[]").lower()
    if not host or host == "localhost" or host.endswith((".local", ".internal", ".localhost")):
        return False
    try:
        ipaddress.ip_address(host)
        return _public_ip(host)
    except ValueError:
        pass
    if host.endswith(".onion"):
        return True
    if "." not in host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        # Non risolvibile da qui: se la rete passa da un proxy la risoluzione avviene lì.
        return True
    return all(_public_ip(info[4][0]) for info in infos)


def url_allowed(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme in {"data", "blob", "about"}:
        return True
    if parts.scheme not in {"http", "https", "ws", "wss"}:
        return False
    return host_is_public(parts.hostname or "")
