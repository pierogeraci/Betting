"""Accesso dei contenitori di raccolta al resto del sistema.

È tutto ciò che un contenitore di raccolta può fare: prendere un lavoro, chiuderlo,
scrivere file nel secchio di arrivo. Non importa SQLAlchemy né i modelli.
"""

from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from typing import Any

from core.config import get_settings
from core.storage import ObjectStore, S3Store


@dataclass
class CollectJob:
    id: int
    kind: str
    payload: dict[str, Any]
    attempts: int


class CollectClient:
    def __init__(
        self, dsn: str | None = None, store: ObjectStore | None = None, worker: str | None = None
    ) -> None:
        settings = get_settings()
        self._dsn = dsn or settings.collect_database_url
        self._bucket = settings.s3_inbox_bucket
        self._store = store or S3Store(
            settings.s3_endpoint,
            settings.collect_s3_access_key,
            settings.collect_s3_secret_key,
            settings.s3_region,
        )
        self.worker = worker or f"{socket.gethostname()}:{os.getpid()}"

    def _connect(self):
        import psycopg

        return psycopg.connect(self._dsn, autocommit=True)

    def claim(self, kinds: list[str], lease_seconds: int = 300) -> CollectJob | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, tipo, carico, tentativi FROM lavoro_prendi(%s, %s, %s)",
                (kinds, self.worker, lease_seconds),
            ).fetchone()
        if row is None:
            return None
        return CollectJob(id=row[0], kind=row[1], payload=row[2] or {}, attempts=row[3])

    def close(
        self, job_id: int, ok: bool, result: dict[str, Any] | None = None, error: str | None = None
    ) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT lavoro_chiudi(%s, %s, %s, %s::jsonb, %s)",
                (job_id, self.worker, ok, json.dumps(result or {}), error),
            ).fetchone()
        return bool(row and row[0])

    def read_work(self, key: str) -> bytes:
        """Legge un file dal secchio di lavorazione: l'unico che i contenitori di estrazione e APK possono leggere."""
        return self._store.get(get_settings().s3_work_bucket, key)

    def upload(
        self, job_id: int, name: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> str:
        key = f"{job_id}/{name}"
        self._store.put(self._bucket, key, data, content_type)
        return key
