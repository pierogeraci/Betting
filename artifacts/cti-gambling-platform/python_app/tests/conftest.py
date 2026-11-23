"""Fixture comuni. I test usano un database `betting_test` locale e un archivio in memoria.
Nessuna richiesta di rete."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"


def _dotenv() -> dict[str, str]:
    path = ROOT / ".env"
    if not path.exists():
        return {}
    pairs = (
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line and not line.startswith("#")
    )
    return {k.strip(): v.strip() for k, v in pairs}


def _test_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        base = (
            os.environ.get("DATABASE_URL")
            or _dotenv().get("DATABASE_URL")
            or "postgresql://betting:betting@localhost:5432/betting"
        )
        url = base.rsplit("/", 1)[0] + "/betting_test"
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


os.environ["DATABASE_URL"] = _test_url()
os.environ.setdefault("S3_BUCKET", "prova-grezzi")
# Nessun download di modelli e nessun servizio esterno durante i test.
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["MODELLI_SOLO_LOCALI"] = "1"
os.environ["OLLAMA_URL"] = ""
os.environ.setdefault("S3_BUCKET_ARRIVO", "prova-arrivo")


@pytest.fixture(scope="session")
def engine():
    from alembic import command
    from alembic.config import Config

    url = _test_url()
    admin = create_engine(url.rsplit("/", 1)[0] + "/postgres", isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text("DROP DATABASE IF EXISTS betting_test WITH (FORCE)"))
            conn.execute(text("CREATE DATABASE betting_test"))
    except Exception as exc:  # noqa: BLE001
        pytest.exit(
            f"Database di prova non raggiungibile: avvia `docker compose up -d db`. ({exc})", returncode=2
        )
    finally:
        admin.dispose()
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture()
def store():
    from core import storage

    memory = storage.MemoryStore()
    storage.set_store(memory)
    yield memory
    storage.set_store(None)


@pytest.fixture()
def db(engine, store):
    """Sessione dentro una transazione che viene annullata a fine test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def fixture_bytes():
    def read(relative: str) -> bytes:
        return (FIXTURES / relative).read_bytes()

    return read
