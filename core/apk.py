"""Analisi delle app Android (Fase 4): accodamento e acquisizione."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from core import queue
from core.config import get_settings
from core.models import Lavoro, Media
from core.storage import get_store, read_archive


def request_apk_analysis(session: Session, media: Media, user_id: int | None = None) -> Lavoro | None:
    """Copia l'APK nel secchio di lavorazione e accoda l'analisi statica nel contenitore MobSF."""
    pending = session.execute(
        select(Lavoro.id).where(
            Lavoro.tipo == "apk",
            Lavoro.carico["media_id"].astext == str(media.id),
            Lavoro.stato.in_(["in_attesa", "in_corso"]),
        )
    ).first()
    if pending:
        return None
    settings = get_settings()
    store = get_store()
    if not store.exists(settings.s3_work_bucket, media.sha256):
        store.put(
            settings.s3_work_bucket,
            media.sha256,
            read_archive(media.oggetto_chiave),
            "application/vnd.android.package-archive",
        )
    return queue.enqueue(
        session,
        queue=queue.COLLECT,
        kind="apk",
        payload={"media_id": media.id, "chiave": media.sha256, "nome": media.nome_file},
        next_kind="acquisisci_apk",
        user_id=user_id,
        max_attempts=2,
    )
