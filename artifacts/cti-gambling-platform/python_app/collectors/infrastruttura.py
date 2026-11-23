"""Area infrastruttura e segnali per i domini gemelli.

Dallo snapshot: identificativi di tracciamento, impronta della struttura HTML,
hash dell'icona, domini contattati. Dai dati di rete raccolti dal contenitore di
raccolta (DNS, certificato, registrazione), se presenti nella vista.
"""

from __future__ import annotations

import hashlib
import re

from collectors.base import ND, PRESENTE, Indicator, Page, evidence
from core.domains import registrable_domain

NOME = "infrastruttura"
VERSIONE = "1"
AREA = "Infrastruttura"

TRACKING = {
    "google_analytics": re.compile(r"\b(UA-\d{4,10}-\d{1,4}|G-[A-Z0-9]{8,12})\b"),
    "google_tag_manager": re.compile(r"\b(GTM-[A-Z0-9]{5,9})\b"),
    "google_ads": re.compile(r"\b(AW-\d{8,12})\b"),
    "facebook_pixel": re.compile(r"fbq\(\s*['\"]init['\"]\s*,\s*['\"](\d{12,20})['\"]"),
    "yandex_metrica": re.compile(r"ym\(\s*(\d{6,10})\s*,\s*['\"]init"),
    "hotjar": re.compile(r"hjid\s*[:=]\s*(\d{5,10})"),
    "tiktok_pixel": re.compile(r"ttq\.load\(\s*['\"]([A-Z0-9]{15,25})['\"]"),
}


def tracking_ids(page: Page) -> dict[str, list[str]]:
    blob = page.html or ""
    found: dict[str, list[str]] = {}
    for name, regex in TRACKING.items():
        values = sorted(set(regex.findall(blob)))
        if values:
            found[name] = values
    return found


def structure_fingerprint(page: Page) -> str | None:
    """Impronta della sequenza di tag: pagine dello stesso modello danno impronte uguali."""
    tags = page.parsed.tags
    if len(tags) < 10:
        return None
    shingles = {" ".join(tags[i : i + 4]) for i in range(len(tags) - 3)}
    # SimHash a 64 bit sulle sequenze di quattro tag.
    vector = [0] * 64
    for sh in shingles:
        h = int.from_bytes(hashlib.sha256(sh.encode()).digest()[:8], "big")
        for bit in range(64):
            vector[bit] += 1 if h >> bit & 1 else -1
    value = sum(1 << bit for bit in range(64) if vector[bit] > 0)
    return f"{value:016x}"


def simhash_distance(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def _ind(code: str, value: str, certainty: float, ev: dict | None = None) -> Indicator:
    return Indicator(code, value, certainty, NOME, VERSIONE, ev or {}, AREA)


def collect(pages: list[Page]) -> list[Indicator]:
    ok = [p for p in pages if p.status == "riuscito" and p.html]
    if not ok:
        return [
            _ind(c, ND, 0.0, {"motivo": "Nessuna pagina letta"})
            for c in (
                "identificativi_tracciamento",
                "impronta_html",
                "domini_terze_parti",
                "icona_sito",
                "dati_rete",
            )
        ]
    out: list[Indicator] = []
    home = ok[0]
    ids: dict[str, list[str]] = {}
    for p in ok:
        for k, v in tracking_ids(p).items():
            ids[k] = sorted(set(ids.get(k, []) + v))
    if ids:
        flat = ", ".join(f"{k}: {'/'.join(v)}" for k, v in ids.items())
        out.append(
            _ind("identificativi_tracciamento", PRESENTE, 1.0, evidence(home, flat, identificativi=ids))
        )
    else:
        out.append(
            _ind(
                "identificativi_tracciamento",
                ND,
                0.0,
                {"motivo": "Nessun identificativo di tracciamento noto"},
            )
        )
    fp = structure_fingerprint(home)
    if fp:
        out.append(
            _ind(
                "impronta_html", PRESENTE, 1.0, evidence(home, f"SimHash della struttura: {fp}", impronta=fp)
            )
        )
    else:
        out.append(_ind("impronta_html", ND, 0.0, {"motivo": "Pagina troppo povera di struttura"}))
    base = registrable_domain(home.host) if home.host else ""
    third = sorted(
        {registrable_domain(h) for p in ok for h in p.all_hosts if h and registrable_domain(h) != base}
    )
    if third:
        out.append(
            _ind(
                "domini_terze_parti", PRESENTE, 1.0, evidence(home, ", ".join(third[:15]), domini=third[:100])
            )
        )
    else:
        out.append(_ind("domini_terze_parti", ND, 0.0, {"motivo": "Traffico non registrato"}))
    icon = home.extra.get("icona_sha256")
    if icon:
        out.append(
            _ind("icona_sito", PRESENTE, 1.0, evidence(home, f"sha256 dell'icona {icon[:16]}…", hash=icon))
        )
    else:
        out.append(_ind("icona_sito", ND, 0.0, {"motivo": "Icona non archiviata"}))
    net = home.extra.get("rete") or {}
    if net:
        bits = []
        if net.get("ip"):
            bits.append("IP " + ", ".join(net["ip"][:4]))
        if net.get("ns"):
            bits.append("NS " + ", ".join(net["ns"][:3]))
        if net.get("registrar"):
            bits.append("registrar " + net["registrar"])
        if net.get("certificato", {}).get("emittente"):
            bits.append("certificato di " + net["certificato"]["emittente"])
        out.append(
            _ind(
                "dati_rete", PRESENTE, 0.9, evidence(home, "; ".join(bits) or "Dati di rete raccolti", **net)
            )
        )
    else:
        out.append(_ind("dati_rete", ND, 0.0, {"motivo": "Dati DNS e di registrazione non ancora raccolti"}))
    return out
