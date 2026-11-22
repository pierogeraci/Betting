"""Configurazione letta dall'ambiente. I segreti stanno in `.env`, mai nel codice."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _flag(name: str, default: bool = False) -> bool:
    raw = _env(name)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "si", "sì", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str
    collect_database_url: str
    s3_endpoint: str
    s3_region: str
    s3_archive_bucket: str
    s3_inbox_bucket: str
    s3_access_key: str
    s3_secret_key: str
    collect_s3_access_key: str
    collect_s3_secret_key: str
    secure_cookies: bool
    session_hours: int
    max_upload_mb: int
    # Vero quando il traffico passa da un proxy che sostituisce i certificati:
    # le evidenze basate sul certificato TLS non sono valide.
    intercepted_network: bool
    collect_proxy: str
    collect_pages_per_hour: int
    adm_max_age_days: int


def _sqlalchemy_url(url: str) -> str:
    # Si accetta la forma classica postgresql:// e la si porta al driver psycopg 3.
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


@lru_cache
def get_settings() -> Settings:
    return Settings(
        database_url=_sqlalchemy_url(
            _env("DATABASE_URL", "postgresql://betting:betting@localhost:5432/betting")
        ),
        collect_database_url=_env("RACCOLTA_DATABASE_URL"),
        s3_endpoint=_env("S3_ENDPOINT", "http://localhost:8333"),
        s3_region=_env("S3_REGION", "us-east-1"),
        s3_archive_bucket=_env("S3_BUCKET", "betting-grezzi"),
        s3_inbox_bucket=_env("S3_BUCKET_ARRIVO", "betting-arrivo"),
        s3_access_key=_env("S3_ACCESS_KEY"),
        s3_secret_key=_env("S3_SECRET_KEY"),
        collect_s3_access_key=_env("RACCOLTA_S3_ACCESS_KEY"),
        collect_s3_secret_key=_env("RACCOLTA_S3_SECRET_KEY"),
        secure_cookies=_flag("COOKIE_SICURI", False),
        session_hours=int(_env("SESSIONE_ORE", "12")),
        max_upload_mb=int(_env("CARICAMENTO_MAX_MB", "200")),
        intercepted_network=_flag("RETE_INTERCETTATA", False),
        collect_proxy=_env("RACCOLTA_PROXY"),
        collect_pages_per_hour=int(_env("RACCOLTA_MAX_PAGINE_ORA", "120")),
        adm_max_age_days=int(_env("ADM_GIORNI_VALIDITA", "30")),
    )
