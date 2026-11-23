"""Criterio di uscita della Fase 0: un URL inserito a mano produce snapshot e confronto con ADM.

Si esegue con `make test-integration`, dopo che il contenitore di raccolta ha
elaborato gli URL di PROVA_URLS.
"""

from __future__ import annotations

import os
import time

import pytest
from sqlalchemy import select

from core import adm
from core.db import session_scope
from core.domains import normalize_url
from core.models import Indicatore, Lavoro, Sito, Snapshot
from core.storage import read_archive, sha256_hex

pytestmark = pytest.mark.integration
URLS = [u.strip() for u in os.environ.get("PROVA_URLS", "").split(",") if u.strip()]


@pytest.fixture(scope="module", autouse=True)
def wait_for_internal_queue():
    deadline = time.time() + 120
    while time.time() < deadline:
        with session_scope() as session:
            pending = session.execute(
                select(Lavoro.id).where(Lavoro.coda == "interna", Lavoro.stato.in_(["in_attesa", "in_corso"]))
            ).first()
        if not pending:
            return
        time.sleep(2)
    pytest.fail("La coda interna non si è svuotata: il lavoratore è avviato?")


def test_urls_configured():
    assert 1 <= len(URLS) <= 3


@pytest.mark.parametrize("url", URLS)
def test_url_produces_snapshot_and_adm_comparison(url):
    domain = normalize_url(url).registrable
    with session_scope() as session:
        site = session.execute(select(Sito).where(Sito.dominio == domain)).scalar_one()
        snapshot = session.execute(
            select(Snapshot).where(Snapshot.sito_id == site.id).order_by(Snapshot.raccolto_il.desc()).limit(1)
        ).scalar_one()
        # Lo snapshot esiste sempre: riuscito, bloccato o errore sono tutti esiti registrati.
        assert snapshot.stato in {"riuscito", "bloccato", "errore"}
        assert snapshot.raccolto_il.tzinfo is not None and len(snapshot.sha256) == 64
        if snapshot.stato == "riuscito":
            assert snapshot.html_chiave and snapshot.schermata_chiave
            assert sha256_hex(read_archive(snapshot.html_chiave)) == snapshot.html_sha256
            assert read_archive(snapshot.schermata_chiave)[:8] == b"\x89PNG\r\n\x1a\n"
        indicators = {
            i.codice: i
            for i in session.execute(
                select(Indicatore).where(Indicatore.sito_id == site.id).order_by(Indicatore.id)
            ).scalars()
        }
        for kind, code in adm.CODES.items():
            indicator = indicators[code]
            assert indicator.valore in {"presente", "assente", "non_determinabile"}
            # "Assente" è ammesso solo se l'elenco è caricato; altrimenti il dato non è determinabile.
            if adm.current_load(session, kind) is None:
                assert indicator.valore == "non_determinabile"
            else:
                assert indicator.evidenza.get("versione_elenco")
        print(
            f"\n{domain}: snapshot {snapshot.stato} ({snapshot.motivo or snapshot.errore or snapshot.codice_http}), ADM {site.esito_adm}"
        )
