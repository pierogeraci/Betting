"""Acquisizione dei risultati delle sonde Telegram, web e Tor (lato interno).

Come per gli snapshot, il manifesto viene da un contenitore che ha letto contenuti
esterni: si validano i campi e si ricalcolano gli hash dei file.
"""

from __future__ import annotations

import hashlib
import mimetypes
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from core import discovery
from core.config import get_settings
from core.ingest import IngestError, _read_manifest, _text
from core.keywords import active_keywords
from core.models import Avviso, Canale, Lavoro, Media, Sonda, utcnow
from core.storage import archive_bytes, get_store, sha256_hex

MAX_WAIT_SECONDS = 86_400


def _probe(session: Session, origin: Lavoro) -> Sonda | None:
    probe_id = origin.carico.get("sonda_id")
    return session.get(Sonda, int(probe_id)) if probe_id else None


def _finish_probe(
    session: Session, probe: Sonda | None, manifest: dict[str, Any], stats: discovery.RunStats
) -> None:
    if probe is None:
        return
    probe.ultima_esecuzione = utcnow()
    wait = manifest.get("attesa")
    if isinstance(wait, int) and wait > 0:
        # Telegram ha chiesto di attendere: la sonda non riparte prima.
        probe.disponibile_dal = utcnow() + timedelta(seconds=min(wait, MAX_WAIT_SECONDS))
        session.add(
            Avviso(
                tipo="sonda",
                titolo=f"Sonda {probe.nome}: attesa di {wait} secondi chiesta dal servizio",
                testo="La sonda riprende da sola allo scadere dell'attesa.",
            )
        )
    if manifest.get("esito") != "riuscito":
        probe.ultimo_errore = (
            "; ".join(str(e) for e in manifest.get("errori", []))[:2000] or "Esecuzione non riuscita"
        )
        probe.stato = "in_errore"
    else:
        probe.ultimo_errore = "; ".join(stats.errors[:5]) or None
    probe.cursore = dict(probe.cursore or {}) | {
        "ultimo_esito": stats.as_dict(),
        "ultimo_lavoro": manifest.get("_lavoro"),
    }


def _cleanup(job_id: int, names: list[str]) -> None:
    store = get_store()
    bucket = get_settings().s3_inbox_bucket
    for name in names + ["manifesto.json"]:
        store.delete(bucket, f"{job_id}/{name}")


def ingest_telegram(session: Session, origin: Lavoro) -> dict[str, Any]:
    manifest = _read_manifest(origin.id)
    manifest["_lavoro"] = origin.id
    probe = _probe(session, origin)
    stats = discovery.RunStats()
    keywords = active_keywords(session)
    max_new = int((probe.configurazione or {}).get("max_siti_nuovi", 30)) if probe else 30
    files: list[str] = []
    channels = {
        str(c.id): c
        for c in session.query(Canale).filter(
            Canale.id.in_([int(k) for k in (manifest.get("canali") or {}) if str(k).isdigit()] or [0])
        )
    }
    for cid, info in (manifest.get("canali") or {}).items():
        channel = channels.get(str(cid))
        if channel is None or not isinstance(info, dict):
            continue
        channel.ultimo_controllo = utcnow()
        if info.get("errore"):
            channel.ultimo_errore = _text(info["errore"], 500)
            if "pubblico" in str(info["errore"]):
                # Non è un canale pubblico: può essere l'account di una persona. Il nome non si conserva.
                channel.stato = "rifiutato"
                channel.motivo = "Non è un canale o gruppo pubblico: nome cancellato"
                channel.identificativo = "rimosso-" + sha256_hex(channel.identificativo.encode())[:16]
                channel.titolo = ""
            continue
        channel.titolo = _text(info.get("titolo"), 300) or channel.titolo
        channel.tipo = info.get("tipo") if info.get("tipo") in {"canale", "gruppo"} else channel.tipo
        channel.partecipanti = (
            info.get("partecipanti") if isinstance(info.get("partecipanti"), int) else channel.partecipanti
        )
        channel.ultimo_errore = None
    for message in manifest.get("messaggi") or []:
        if not isinstance(message, dict) or not isinstance(message.get("id"), int):
            continue
        name = _text(message.get("canale"), 120) or ""
        text = _text(message.get("testo"), 20000) or ""
        links = [str(link)[:2000] for link in (message.get("link") or [])[:50]]
        reference = f"https://t.me/{name}/{message['id']}"
        digest = sha256_hex(f"telegram|{name}|{message['id']}|{text}".encode())
        try:
            at = datetime.fromisoformat(str(message.get("data")))
        except ValueError:
            at = None
        element, created = discovery.store_element(
            session,
            source="telegram",
            kind="messaggio",
            reference=reference,
            content=text,
            digest=digest,
            probe_id=probe.id if probe else None,
            collected_at=None,
            metadata={
                "canale": name,
                "canale_id": message.get("canale_id"),
                "messaggio_id": message["id"],
                "pubblicato_il": at.isoformat() if at else None,
                "link": links,
                "inoltrato_da_canale": message.get("inoltrato_da_canale")
                if isinstance(message.get("inoltrato_da_canale"), int)
                else None,
                "visualizzazioni": message.get("visualizzazioni")
                if isinstance(message.get("visualizzazioni"), int)
                else None,
                "media_non_scaricato": _text(
                    message.get("media_non_scaricato") or message.get("media_saltato"), 120
                ),
            },
        )
        if not created:
            stats.duplicates += 1
            continue
        stats.elements += 1
        for media in (message.get("media") or [])[:5]:
            if not isinstance(media, dict) or not media.get("nome") or "/" in str(media["nome"]):
                continue
            files.append(media["nome"])
            data = get_store().get(get_settings().s3_inbox_bucket, f"{origin.id}/{media['nome']}")
            if media.get("sha256") != hashlib.sha256(data).hexdigest():
                stats.errors.append(f"Hash non corrispondente per {media['nome']}")
                continue
            mime = (
                _text(media.get("mime"), 120)
                or mimetypes.guess_type(media["nome"])[0]
                or "application/octet-stream"
            )
            digest, key = archive_bytes(data, mime)
            session.add(
                Media(
                    elemento_grezzo_id=element.id,
                    tipo=media.get("tipo")
                    if media.get("tipo") in {"immagine", "video", "audio", "documento"}
                    else "documento",
                    mime=mime,
                    nome_file=str(media["nome"])[:200],
                    dimensione=len(data),
                    sha256=digest,
                    oggetto_chiave=key,
                )
            )
        discovery.process_text(
            session,
            element,
            text + "\n" + "\n".join(links),
            stats,
            keywords=keywords,
            source_label="telegram",
            max_new_sites=max_new,
            platform="telegram",
            extra_urls=links,
        )
    for cid, cursor in (manifest.get("cursori") or {}).items():
        channel = channels.get(str(cid))
        if channel is not None and isinstance(cursor, int) and cursor > (channel.cursore or 0):
            channel.cursore = cursor
    session.flush()
    # Estrazione multimediale dei file scaricati (Fase 3).
    from core import queue
    from core.models import ElementoGrezzo

    for media in (
        session.query(Media)
        .join(ElementoGrezzo)
        .filter(
            ElementoGrezzo.sonda_id == (probe.id if probe else None),
            Media.creato_il >= utcnow() - timedelta(minutes=10),
        )
    ):
        if media.tipo in {"immagine", "video", "audio"}:
            queue.enqueue(
                session,
                queue=queue.COLLECT,
                kind="estrai_media",
                payload={
                    "media_id": media.id,
                    "chiave": media.oggetto_chiave,
                    "tipo": media.tipo,
                    "mime": media.mime,
                },
                next_kind="acquisisci_estrazione",
                max_attempts=2,
            )
    _finish_probe(session, probe, manifest, stats)
    _cleanup(origin.id, files)
    return stats.as_dict()


def ingest_crawl(session: Session, origin: Lavoro) -> dict[str, Any]:
    manifest = _read_manifest(origin.id)
    manifest["_lavoro"] = origin.id
    probe = _probe(session, origin)
    stats = discovery.RunStats()
    keywords = active_keywords(session)
    source = "tor" if origin.carico.get("tor") else "web"
    max_new = int((probe.configurazione or {}).get("max_siti_nuovi", 30)) if probe else 30
    blocked = 0
    for page in manifest.get("pagine") or []:
        if not isinstance(page, dict) or not page.get("url"):
            continue
        url = _text(page.get("url"), 2000) or ""
        text = _text(page.get("testo"), 20000) or ""
        digest = str(page.get("sha256") or sha256_hex((url + text).encode()))[:64]
        if page.get("bloccato"):
            blocked += 1
        element, created = discovery.store_element(
            session,
            source=source,
            kind="pagina",
            reference=url,
            content=text,
            digest=digest,
            probe_id=probe.id if probe else None,
            metadata={
                "titolo": _text(page.get("titolo"), 300),
                "codice_http": page.get("codice_http") if isinstance(page.get("codice_http"), int) else None,
                "bloccato": _text(page.get("bloccato"), 60),
                "parole": [str(w)[:60] for w in (page.get("parole") or [])[:30]],
                "link_esterni": len(page.get("link_esterni") or []),
            },
        )
        if not created:
            stats.duplicates += 1
            continue
        stats.elements += 1
        if page.get("bloccato"):
            continue
        links = [str(link)[:2000] for link in (page.get("link_esterni") or [])[:150]]
        discovery.process_text(
            session,
            element,
            text,
            stats,
            keywords=keywords,
            source_label=source,
            max_new_sites=max_new,
            extra_urls=links,
        )
    if blocked:
        stats.errors.append(f"{blocked} pagine bloccate: non ritentate")
    _finish_probe(session, probe, manifest, stats)
    _cleanup(origin.id, [])
    if manifest.get("esito") != "riuscito" and not manifest.get("pagine"):
        raise IngestError(
            "Crawler non riuscito: " + "; ".join(str(e)[:300] for e in manifest.get("errori", []))
        )
    return stats.as_dict()
