"""Accodamento dell'estrazione multimediale e acquisizione dei risultati."""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from core import queue
from core.config import get_settings
from core.ingest import IngestError, _read_manifest, _text
from core.models import Estrazione, Lavoro, Media
from core.storage import archive_bytes, get_store, read_archive

KINDS = {"ocr", "qr", "logo", "trascrizione", "traduzione"}


def request_extraction(
    session: Session, media: Media, translate: bool = False, user_id: int | None = None
) -> Lavoro | None:
    """Copia il file nel secchio di lavorazione (l'unico che il contenitore di estrazione può leggere) e accoda il lavoro."""
    if media.tipo not in {"immagine", "video", "audio"}:
        return None
    pending = session.execute(
        select(Lavoro.id).where(
            Lavoro.tipo == "estrai_media",
            Lavoro.carico["media_id"].astext == str(media.id),
            Lavoro.stato.in_(["in_attesa", "in_corso"]),
        )
    ).first()
    if pending:
        return None
    settings = get_settings()
    key = f"{media.sha256}"
    store = get_store()
    if not store.exists(settings.s3_work_bucket, key):
        store.put(settings.s3_work_bucket, key, read_archive(media.oggetto_chiave), media.mime)
    return queue.enqueue(
        session,
        queue=queue.COLLECT,
        kind="estrai_media",
        payload={"media_id": media.id, "chiave": key, "tipo": media.tipo, "traduci": translate},
        next_kind="acquisisci_estrazione",
        user_id=user_id,
        max_attempts=2,
    )


def ingest_extraction(session: Session, origin: Lavoro) -> dict[str, Any]:
    manifest = _read_manifest(origin.id)
    media = session.get(Media, int(origin.carico.get("media_id") or 0))
    if media is None:
        raise IngestError("File di origine non trovato")
    settings = get_settings()
    store = get_store()
    count = 0
    for item in (manifest.get("estrazioni") or [])[:2000]:
        if not isinstance(item, dict) or item.get("tipo") not in KINDS:
            continue
        start = item.get("inizio_ms") if isinstance(item.get("inizio_ms"), int) else None
        end = item.get("fine_ms") if isinstance(item.get("fine_ms"), int) else None
        meta = item.get("metadati") if isinstance(item.get("metadati"), dict) else {}
        session.add(
            Estrazione(
                elemento_grezzo_id=media.elemento_grezzo_id,
                media_id=media.id,
                tipo=item["tipo"],
                testo=_text(item.get("testo"), 20000) or "",
                tempo_inizio_ms=start,
                tempo_fine_ms=end,
                modello=_text(item.get("modello"), 80) or "",
                versione_modello="1",
                metadati=meta,
            )
        )
        count += 1
    frames = []
    for frame in (manifest.get("fotogrammi") or [])[:12]:
        if not isinstance(frame, dict) or "/" in str(frame.get("nome", "")):
            continue
        data = store.get(settings.s3_inbox_bucket, f"{origin.id}/{frame['nome']}")
        if hashlib.sha256(data).hexdigest() != frame.get("sha256"):
            continue
        digest, key = archive_bytes(data, "image/jpeg")
        time_ms = (
            int(str(frame["nome"]).split("_")[-1].split(".")[0])
            if str(frame["nome"]).split("_")[-1].split(".")[0].isdigit()
            else 0
        )
        frames.append({"chiave": key, "sha256": digest, "tempo_ms": time_ms})
        store.delete(settings.s3_inbox_bucket, f"{origin.id}/{frame['nome']}")
    if frames or manifest.get("info") or manifest.get("errori"):
        session.add(
            Estrazione(
                elemento_grezzo_id=media.elemento_grezzo_id,
                media_id=media.id,
                tipo="fotogrammi",
                testo="",
                modello="ffmpeg+phash",
                versione_modello="1",
                metadati={
                    "fotogrammi": frames,
                    "info": manifest.get("info") or {},
                    "errori": [str(e)[:300] for e in (manifest.get("errori") or [])[:10]],
                },
            )
        )
    store.delete(settings.s3_inbox_bucket, f"{origin.id}/manifesto.json")
    store.delete(settings.s3_work_bucket, str(origin.carico.get("chiave", "")))
    queue.enqueue(
        session,
        queue=queue.INTERNAL,
        kind="analizza_testo",
        payload={"elemento_id": media.elemento_grezzo_id},
    )
    session.flush()
    return {"estrazioni": count, "fotogrammi": len(frames)}
