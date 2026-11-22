"""Dalle raccolte delle sonde alla lista dei siti.

Ogni messaggio o pagina raccolta diventa un elemento grezzo. Le entità con forma
fissa (URL, domini, canali, portafogli) entrano nel grafo; i domini nuovi diventano
siti da fotografare, entro un tetto per esecuzione; le parole chiave con avviso
generano un avviso per l'analista.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core import keywords as kw
from core.domains import InvalidUrl, normalize_url
from core.intake import get_or_create_entity, mention, register_url, request_snapshot
from core.models import Avviso, Canale, ElementoGrezzo, Sito
from extractors.entities import extract
from extractors.normalize import normalize_text

# Domini che compaiono ovunque e non sono siti di gioco.
COMMON = {
    "t.me",
    "telegram.me",
    "telegram.org",
    "youtube.com",
    "youtu.be",
    "google.com",
    "instagram.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "wikipedia.org",
    "bit.ly",
    "linktr.ee",
    "whatsapp.com",
    "apple.com",
    "play.google.com",
    "vk.com",
    "reddit.com",
    "github.com",
    "cloudflare.com",
    "w3.org",
    "schema.org",
    "gstatic.com",
}


@dataclass
class RunStats:
    elements: int = 0
    duplicates: int = 0
    new_sites: int = 0
    snapshots: int = 0
    alerts: int = 0
    new_channels: int = 0
    skipped_sites: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "elementi": self.elements,
            "duplicati": self.duplicates,
            "siti_nuovi": self.new_sites,
            "snapshot": self.snapshots,
            "avvisi": self.alerts,
            "canali_nuovi": self.new_channels,
            "siti_oltre_tetto": self.skipped_sites,
            "errori": self.errors[:20],
        }


def store_element(
    session: Session,
    *,
    source: str,
    kind: str,
    reference: str,
    content: str,
    digest: str,
    probe_id: int | None,
    metadata: dict[str, Any],
    collected_at=None,
) -> tuple[ElementoGrezzo, bool]:
    existing = session.execute(
        select(ElementoGrezzo).where(ElementoGrezzo.fonte == source, ElementoGrezzo.sha256 == digest)
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False
    element = ElementoGrezzo(
        sonda_id=probe_id,
        fonte=source,
        tipo=kind,
        riferimento=reference[:2000],
        contenuto=content,
        sha256=digest,
        metadati=metadata,
    )
    if collected_at is not None:
        element.raccolto_il = collected_at
    session.add(element)
    session.flush()
    return element, True


def process_text(
    session: Session,
    element: ElementoGrezzo,
    text: str,
    stats: RunStats,
    *,
    keywords: list[kw.Keyword],
    source_label: str,
    max_new_sites: int,
    platform: str | None = None,
    extra_urls: list[str] | None = None,
    require_keyword: bool = True,
) -> list[kw.Keyword]:
    """Entità, siti e avvisi da un testo raccolto. Restituisce le parole chiave trovate."""
    norm = normalize_text(text, platform)
    hits = kw.matches(text, keywords)
    entities = extract(norm)
    urls = [e.value for e in entities if e.kind == "url"] + list(extra_urls or [])
    domains = {e.value for e in entities if e.kind == "dominio"}
    for e in entities:
        if e.kind in {"url", "dominio"}:
            continue
        if e.kind == "canale_telegram":
            if _candidate_channel(session, e.value, element):
                stats.new_channels += 1
            continue
        mention(session, get_or_create_entity(session, e.kind, e.value), element)
    # Un dominio diventa un sito da fotografare solo se il testo parla di gioco.
    relevant = bool(hits) or not require_keyword
    seen: set[str] = set()
    for raw in urls + [f"https://{d}/" for d in domains]:
        try:
            url = normalize_url(raw)
        except InvalidUrl:
            continue
        if url.registrable in COMMON or url.registrable in seen:
            continue
        seen.add(url.registrable)
        exists = session.execute(select(Sito.id).where(Sito.dominio == url.registrable)).first()
        if not relevant and not exists:
            continue
        if not exists and stats.new_sites >= max_new_sites:
            stats.skipped_sites += 1
            continue
        site = register_url(session, element, url)
        if not exists:
            site.fonte_scoperta = source_label
            stats.new_sites += 1
            request_snapshot(session, site, url.url)
            stats.snapshots += 1
    alerting = [h for h in hits if h.alert]
    if alerting:
        session.add(
            Avviso(
                tipo="parola_chiave",
                titolo=f"{source_label}: «{alerting[0].term}»"
                + (f" e altre {len(alerting) - 1}" if len(alerting) > 1 else ""),
                testo=norm[:600],
                elemento_grezzo_id=element.id,
            )
        )
        stats.alerts += 1
    return hits


def erased_name(name: str) -> str:
    """Impronta non invertibile di un nome cancellato (HMAC con un segreto in .env)."""
    import hashlib
    import hmac
    import os

    secret = os.environ.get("SEGRETO_IMPRONTE", "") or os.environ.get("POSTGRES_PASSWORD", "")
    return "rimosso-" + hmac.new(secret.encode(), name.lower().encode(), hashlib.sha256).hexdigest()[:24]


def erase_channel(session: Session, channel: Canale, reason: str) -> None:
    """Toglie il nome di un canale rifiutato da canale e avvisi: può essere l'account di una persona."""
    name = channel.identificativo
    if name.startswith("rimosso-"):
        return
    channel.identificativo = erased_name(name)
    channel.titolo = ""
    channel.stato = "rifiutato"
    channel.motivo = reason
    for alert in session.execute(select(Avviso).where(Avviso.canale_id == channel.id)).scalars():
        alert.titolo = "Canale rifiutato: nome cancellato"
        alert.testo = ""


def _candidate_channel(session: Session, name: str, element: ElementoGrezzo) -> bool:
    """Un canale scoperto entra in stato da_approvare: lo attiva l'analista."""
    if name.startswith("+"):
        return False  # link d'invito: gruppo privato, escluso
    if session.execute(select(Canale.id).where(Canale.identificativo == erased_name(name))).first():
        return False  # già rifiutato: non rientra
    result = session.execute(
        insert(Canale)
        .values(
            piattaforma="telegram",
            identificativo=name.lower(),
            stato="da_approvare",
            scoperto_da=element.id,
            motivo=f"Citato in {element.fonte} {element.riferimento[:200]}",
        )
        .on_conflict_do_nothing()
        .returning(Canale.id)
    ).first()
    if result:
        # Il nome resta solo nella tabella dei canali: potrebbe essere l'account di una persona,
        # e in quel caso viene cancellato quando la sonda verifica che non è un canale pubblico.
        session.add(
            Avviso(
                tipo="canale_scoperto",
                # Il nome non entra nell'avviso: si legge dal canale finché non viene rifiutato.
                titolo="Nuovo canale da approvare",
                testo=f"Citato in {element.riferimento[:300]}",
                elemento_grezzo_id=element.id,
                canale_id=result[0],
            )
        )
        return True
    return False
