"""Inizializzazione applicativa idempotente; lo schema è gestito da Drizzle."""

from __future__ import annotations

import os

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core.db import session_scope
from core.models import ParolaChiave, Sonda, Utente, utcnow
from core.security import create_user

PAROLE_INIZIALI = [
    ("scommesse", "gioco", "it"),
    ("scommessa", "gioco", "it"),
    ("casinò", "gioco", "it"),
    ("casino", "gioco", "en"),
    ("slot", "gioco", "it"),
    ("quote", "gioco", "it"),
    ("bonus benvenuto", "promozione", "it"),
    ("bonus di benvenuto", "promozione", "it"),
    ("free spin", "promozione", "en"),
    ("giri gratis", "promozione", "it"),
    ("betting", "gioco", "en"),
    ("sportsbook", "gioco", "en"),
    ("bookmaker", "gioco", "it"),
    ("poker", "gioco", "it"),
    ("roulette", "gioco", "it"),
    ("crash", "gioco", "en"),
    ("partite truccate", "frode", "it"),
    ("fixed matches", "frode", "en"),
    ("sure win", "frode", "en"),
    ("combine", "frode", "it"),
    ("no kyc", "anonimato", "en"),
    ("senza documenti", "anonimato", "it"),
    ("anonimo", "anonimato", "it"),
    ("bitcoin", "pagamento", "en"),
    ("usdt", "pagamento", "en"),
    ("crypto casino", "gioco", "en"),
    ("deposito minimo", "promozione", "it"),
    ("codice promo", "promozione", "it"),
    ("aams", "titolo", "it"),
    ("adm", "titolo", "it"),
]

SONDE_INIZIALI = [
    {
        "nome": "manuale",
        "tipo": "manuale",
        "configurazione": {},
        "cursore": {},
        "stato": "attiva",
    },
    {
        "nome": "adm",
        "tipo": "adm",
        "configurazione": {},
        "cursore": {},
        "stato": "attiva",
    },
    {
        "nome": "telegram",
        "tipo": "telegram",
        "configurazione": {
            "intervallo_minuti": 30,
            "messaggi_per_canale": 200,
            "scarica_media": True,
            "max_media_mb": 25,
            "max_siti_nuovi": 30,
        },
        "cursore": {},
        "stato": "in_pausa",
    },
    {
        "nome": "web",
        "tipo": "web",
        "configurazione": {
            "intervallo_minuti": 1440,
            "semi": [],
            "profondita": 1,
            "max_pagine": 40,
            "max_siti_nuovi": 30,
        },
        "cursore": {},
        "stato": "in_pausa",
    },
    {
        "nome": "tor",
        "tipo": "tor",
        "configurazione": {
            "intervallo_minuti": 1440,
            "semi": [],
            "profondita": 1,
            "max_pagine": 30,
            "max_siti_nuovi": 30,
        },
        "cursore": {},
        "stato": "in_pausa",
    },
]


def _seed_default_data(db: Session) -> None:
    db.execute(
        insert(Sonda)
        .values([{**sonda, "creato_il": utcnow()} for sonda in SONDE_INIZIALI])
        .on_conflict_do_nothing(index_elements=[Sonda.nome])
    )
    db.execute(
        insert(ParolaChiave)
        .values(
            [
                {
                    "termine": termine,
                    "categoria": categoria,
                    "lingua": lingua,
                    "attiva": True,
                    "avviso": categoria == "frode",
                    "creato_il": utcnow(),
                }
                for termine, categoria, lingua in PAROLE_INIZIALI
            ]
        )
        .on_conflict_do_nothing(index_elements=[ParolaChiave.termine])
    )


def inizializza_portale() -> None:
    """Crea solo righe iniziali; non crea o modifica lo schema PostgreSQL."""
    with session_scope() as db:
        _seed_default_data(db)
        if db.execute(select(Utente.id).limit(1)).first():
            return

        username = os.environ.get("LOCAL_AUTH_ADMIN_USER_ID", "").strip()
        password = os.environ.get("LOCAL_AUTH_ADMIN_PASSWORD", "")
        if not username or not password:
            raise RuntimeError(
                "Credenziali iniziali mancanti: configura i segreti di accesso locale."
            )
        create_user(db, username, password, role="amministratore")
