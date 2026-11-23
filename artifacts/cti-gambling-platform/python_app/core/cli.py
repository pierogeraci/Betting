"""Comandi di amministrazione. Uso: python -m core.cli <comando>."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
import time

from sqlalchemy import select, text

from core import adm, queue
from core.config import get_settings
from core.db import get_engine, session_scope
from core.models import Lavoro, Utente
from core.security import create_user
from core.storage import get_store


def migrate() -> None:
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config("alembic.ini"), "head")


def wait_for_db(seconds: int = 60) -> None:
    deadline = time.time() + seconds
    while True:
        try:
            with get_engine().connect() as conn:
                conn.execute(text("select 1"))
            return
        except Exception:  # noqa: BLE001
            if time.time() > deadline:
                raise
            time.sleep(1)


def init() -> None:
    """Migrazioni, password del ruolo di raccolta, secchi dell'archivio."""
    wait_for_db()
    migrate()
    password = os.environ.get("RACCOLTA_DB_PASSWORD", "")
    if password:
        with get_engine().begin() as conn:
            quoted = conn.execute(text("select quote_literal(:p)"), {"p": password}).scalar()
            conn.execute(text(f"ALTER ROLE raccolta LOGIN PASSWORD {quoted}"))  # noqa: S608
    settings = get_settings()
    store = get_store()
    for bucket in (settings.s3_archive_bucket, settings.s3_inbox_bucket, settings.s3_work_bucket):
        store.ensure_bucket(bucket)
    print("Inizializzazione completata.")


def add_user(args: argparse.Namespace) -> None:
    password = os.environ.get("NUOVA_PASSWORD") or getpass.getpass("Password (almeno 12 caratteri): ")
    with session_scope() as session:
        user = create_user(session, args.nome_utente, password, name=args.nome or "", role=args.ruolo)
        print(f"Creato l'utente {user.nome_utente} ({user.ruolo}).")


def seed_admin() -> None:
    """Crea il primo amministratore solo se gli account del portale sono vuoti."""
    username = os.environ.get("LOCAL_AUTH_ADMIN_USER_ID", "").strip()
    password = os.environ.get("LOCAL_AUTH_ADMIN_PASSWORD", "")
    if not username or not password:
        raise ValueError("Configura le credenziali iniziali del portale nei segreti dell'ambiente.")
    with session_scope() as session:
        if session.execute(select(Utente.id).limit(1)).first():
            print("Il portale ha già un account; nessun account è stato modificato.")
            return
        user = create_user(session, username, password, role="amministratore")
        print(f"Creato l'account amministratore iniziale: {user.nome_utente}.")


def enqueue_probe(args: argparse.Namespace) -> None:
    """Mette in coda una prova della sonda con un tetto esplicito (vincolo 9).

    - adm: uno scaricamento per elenco configurato;
    - telegram: al più LIMITE canali attivi, 50 messaggi ciascuno;
    - web e tor: al più LIMITE pagine.
    """
    from core import scheduler
    from core.models import Sonda
    from core.sources import adm_sources

    limit = args.limite
    with session_scope() as session:
        if args.sonda == "adm":
            count = 0
            for kind, url in adm_sources().items():
                if not url:
                    print(f"Nessun indirizzo configurato per l'elenco {kind}: lo salto.")
                    continue
                pending = session.execute(
                    select(Lavoro.id).where(
                        Lavoro.tipo == "scarica_adm",
                        Lavoro.stato.in_(["in_attesa", "in_corso"]),
                        Lavoro.carico["elenco"].astext == kind,
                    )
                ).first()
                if not pending:
                    queue.enqueue(
                        session,
                        queue=queue.COLLECT,
                        kind="scarica_adm",
                        payload={"elenco": kind, "url": url},
                        next_kind="acquisisci_adm",
                        max_attempts=2,
                    )
                    count += 1
            print(f"Lavori accodati: {count}")
            return
        if args.sonda in {"telegram", "web", "tor"}:
            if not limit:
                raise ValueError("Per una prova reale serve un limite esplicito.")
            probe = session.execute(select(Sonda).where(Sonda.nome == args.sonda)).scalar_one()
            payload = scheduler.build_payload(session, probe)
            if payload is None:
                raise ValueError("La sonda non ha canali attivi o semi configurati.")
            if args.sonda == "telegram":
                payload["canali"] = payload["canali"][:limit]
                payload["messaggi_per_canale"] = min(payload["messaggi_per_canale"], 50)
            else:
                payload["max_pagine"] = min(payload["max_pagine"], limit)
            payload["prova"] = True
            kind, follow = scheduler.PROBE_JOBS[args.sonda]
            queue.enqueue(
                session, queue=queue.COLLECT, kind=kind, payload=payload, next_kind=follow, max_attempts=1
            )
            print(f"Prova accodata con tetto {limit}.")
            return
        print("Per questa sonda non c'è nulla da accodare: lavora sui lavori già in coda.")


def load_adm(args: argparse.Namespace) -> None:
    with open(args.file, "rb") as handle:
        data = handle.read()
    with session_scope() as session:
        load, created = adm.load_list(session, args.elenco, data, filename=os.path.basename(args.file))
        print(f"{args.elenco}: versione {load.versione}, {load.righe_valide} righe valide, nuovo={created}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="core.cli")
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("init")
    sub.add_parser("migrate")
    sub.add_parser("seed-admin")
    user = sub.add_parser("crea-utente")
    user.add_argument("nome_utente")
    user.add_argument("--nome", default="")
    user.add_argument("--ruolo", default="analista", choices=["analista", "amministratore"])
    probe = sub.add_parser("accoda-sonda")
    probe.add_argument("sonda")
    probe.add_argument("--limite", type=int, default=0)
    load = sub.add_parser("carica-adm")
    load.add_argument("elenco", choices=list(adm.ELENCHI))
    load.add_argument("file")
    args = parser.parse_args()
    try:
        {
            "init": lambda a: init(),
            "migrate": lambda a: migrate(),
            "seed-admin": lambda a: seed_admin(),
            "crea-utente": add_user,
            "accoda-sonda": enqueue_probe,
            "carica-adm": load_adm,
        }[args.comando](args)
    except (ValueError, adm.UnsupportedList) as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
