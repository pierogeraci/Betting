"""Dati di rete di un dominio: DNS, registrazione (RDAP pubblico), certificato TLS.

Un dominio per lavoro. Nessun contatto con il sito oltre alla stretta di mano TLS,
fatta con la verifica attiva: un certificato non valido non si legge, si registra
l'errore di verifica come evidenza. Dietro un proxy che sostituisce i certificati
il certificato non si legge affatto: sarebbe quello del proxy.
"""

from __future__ import annotations

import hashlib
import json
import socket
import ssl
import urllib.request
from datetime import UTC, datetime
from typing import Any

from core.collect_client import CollectClient, CollectJob
from core.config import get_settings
from core.domains import InvalidUrl, normalize_host
from probes.snapshot.guard import host_is_public

RDAP = "https://rdap.org/domain/{}"
TIMEOUT = 15


def dns_records(domain: str) -> tuple[dict[str, list[str]], list[str]]:
    import dns.exception
    import dns.resolver

    out: dict[str, list[str]] = {}
    errors: list[str] = []
    resolver = dns.resolver.Resolver()
    resolver.lifetime = 8
    for rtype, key in (("A", "ip"), ("AAAA", "ipv6"), ("NS", "ns"), ("MX", "mx")):
        try:
            answer = resolver.resolve(domain, rtype)
            out[key] = sorted(str(r).rstrip(".") for r in answer)[:20]
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            out[key] = []
        except dns.exception.DNSException as exc:
            errors.append(f"DNS {rtype}: {type(exc).__name__}")
    return out, errors


def parse_rdap(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for event in data.get("events", []):
        key = {"registration": "creato_il", "expiration": "scade_il", "last changed": "aggiornato_il"}.get(
            event.get("eventAction")
        )
        if key:
            out[key] = event.get("eventDate")
    for entity in data.get("entities", []):
        roles = entity.get("roles", [])
        vcard = (entity.get("vcardArray") or [None, []])[1]
        if "registrar" in roles:
            out["registrar"] = next((v[3] for v in vcard if v and v[0] == "fn"), None)
        if "registrant" in roles:
            # Del registrante si conservano solo il paese e se i dati sono schermati: niente nomi.
            out["registrante_paese"] = next(
                (
                    v[1].get("cc")
                    for v in vcard
                    if v and v[0] == "adr" and isinstance(v[1], dict) and v[1].get("cc")
                ),
                None,
            )
            text = json.dumps(entity).lower()
            out["privacy"] = any(w in text for w in ("redacted", "privacy", "proxy", "withheld"))
    return out


def rdap(domain: str) -> tuple[dict[str, Any], list[str]]:
    request = urllib.request.Request(  # noqa: S310 - indirizzo fisso https
        RDAP.format(domain),
        headers={"Accept": "application/rdap+json", "User-Agent": "betting-antifrode/0.1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310 - indirizzo fisso https
            data = json.loads(response.read(2_000_000))
    except Exception as exc:  # noqa: BLE001
        return {}, [f"RDAP: {type(exc).__name__}"]
    return parse_rdap(data), []


def certificate(domain: str) -> tuple[dict[str, Any], list[str]]:
    if not host_is_public(domain):
        return {}, ["Certificato: dominio non pubblico"]
    context = ssl.create_default_context()
    try:
        with (
            socket.create_connection((domain, 443), timeout=TIMEOUT) as sock,
            context.wrap_socket(sock, server_hostname=domain) as tls,
        ):
            der = tls.getpeercert(binary_form=True)
            info = tls.getpeercert()
    except ssl.SSLCertVerificationError as exc:
        return {"valido": False, "errore_verifica": str(exc.verify_message or exc)[:200]}, []
    except OSError as exc:
        return {}, [f"Certificato: {type(exc).__name__}"]

    def flat(field: Any) -> str:
        return ", ".join(f"{k}={v}" for rdn in field or () for k, v in rdn)[:300]

    return {
        "valido": True,
        "emittente": flat(info.get("issuer")),
        "soggetto": flat(info.get("subject")),
        "valido_dal": info.get("notBefore"),
        "valido_al": info.get("notAfter"),
        "impronta_sha256": hashlib.sha256(der).hexdigest(),
        "nomi": ", ".join(v for k, v in info.get("subjectAltName", ()) if k == "DNS")[:1000],
    }, []


def run_job(client: CollectClient, job: CollectJob) -> dict[str, Any]:
    intercepted = get_settings().intercepted_network
    manifest: dict[str, Any] = {
        "raccolto_il": datetime.now(UTC).isoformat(),
        "rete_intercettata": intercepted,
        "errori": [],
    }
    try:
        domain = normalize_host(str(job.payload.get("dominio", "")))
    except InvalidUrl as exc:
        manifest |= {"esito": "errore", "errori": [str(exc)]}
    else:
        net: dict[str, Any] = {}
        records, errors = dns_records(domain)
        net |= records
        manifest["errori"] += errors
        reg, errors = rdap(domain)
        net |= reg
        manifest["errori"] += errors
        if not intercepted:
            cert, errors = certificate(domain)
            if cert:
                net["certificato"] = cert
            manifest["errori"] += errors
        manifest |= {"esito": "riuscito", "rete": net}
    client.upload(job.id, "manifesto.json", json.dumps(manifest).encode(), "application/json")
    return {"esito": manifest["esito"], "errori": len(manifest["errori"])}
