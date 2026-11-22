"""Modello dati. Nomi di tabelle e colonne in italiano, come nella specifica."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSONB, list[Any]: JSONB}


TS = DateTime(timezone=True)

VALORI_INDICATORE = ("presente", "assente", "non_determinabile")


class Utente(Base):
    """Account degli operatori del portale. Non sono dati raccolti."""

    __tablename__ = "utente"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome_utente: Mapped[str] = mapped_column(String(64), unique=True)
    nome: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    ruolo: Mapped[str] = mapped_column(String(20), default="analista")
    attivo: Mapped[bool] = mapped_column(Boolean, default=True)
    tentativi_falliti: Mapped[int] = mapped_column(Integer, default=0)
    bloccato_fino_a: Mapped[datetime | None] = mapped_column(TS)
    creato_il: Mapped[datetime] = mapped_column(TS, default=utcnow)
    __table_args__ = (CheckConstraint("ruolo in ('analista','amministratore')", name="utente_ruolo"),)


class SessioneUtente(Base):
    __tablename__ = "sessione_utente"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    utente_id: Mapped[int] = mapped_column(ForeignKey("utente.id", ondelete="CASCADE"), index=True)
    csrf: Mapped[str] = mapped_column(String(64))
    creata_il: Mapped[datetime] = mapped_column(TS, default=utcnow)
    scade_il: Mapped[datetime] = mapped_column(TS)
    utente: Mapped[Utente] = relationship()


class Sonda(Base):
    __tablename__ = "sonda"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(80), unique=True)
    tipo: Mapped[str] = mapped_column(String(20))
    configurazione: Mapped[dict[str, Any]] = mapped_column(default=dict)
    cursore: Mapped[dict[str, Any]] = mapped_column(default=dict)
    stato: Mapped[str] = mapped_column(String(20), default="attiva")
    ultima_esecuzione: Mapped[datetime | None] = mapped_column(TS)
    ultimo_errore: Mapped[str | None] = mapped_column(Text)
    disponibile_dal: Mapped[datetime | None] = mapped_column(TS)
    creato_il: Mapped[datetime] = mapped_column(TS, default=utcnow)


class ElementoGrezzo(Base):
    __tablename__ = "elemento_grezzo"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sonda_id: Mapped[int | None] = mapped_column(ForeignKey("sonda.id"))
    fonte: Mapped[str] = mapped_column(String(40), index=True)
    tipo: Mapped[str] = mapped_column(String(20))
    riferimento: Mapped[str] = mapped_column(Text, default="")
    contenuto: Mapped[str | None] = mapped_column(Text)
    oggetto_chiave: Mapped[str | None] = mapped_column(String(200))
    sha256: Mapped[str] = mapped_column(String(64))
    raccolto_il: Mapped[datetime] = mapped_column(TS, default=utcnow, index=True)
    inserito_da: Mapped[int | None] = mapped_column(ForeignKey("utente.id"))
    metadati: Mapped[dict[str, Any]] = mapped_column(default=dict)
    media: Mapped[list[Media]] = relationship(back_populates="elemento")
    autore: Mapped[Utente | None] = relationship()
    __table_args__ = (UniqueConstraint("fonte", "sha256", name="elemento_grezzo_fonte_sha256"),)


class Media(Base):
    __tablename__ = "media"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    elemento_grezzo_id: Mapped[int] = mapped_column(ForeignKey("elemento_grezzo.id", ondelete="CASCADE"))
    tipo: Mapped[str] = mapped_column(String(20))
    mime: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    nome_file: Mapped[str] = mapped_column(String(255), default="")
    dimensione: Mapped[int] = mapped_column(BigInteger, default=0)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    oggetto_chiave: Mapped[str] = mapped_column(String(200))
    creato_il: Mapped[datetime] = mapped_column(TS, default=utcnow)
    elemento: Mapped[ElementoGrezzo] = relationship(back_populates="media")
    __table_args__ = (UniqueConstraint("elemento_grezzo_id", "sha256", name="media_elemento_sha256"),)


class Estrazione(Base):
    __tablename__ = "estrazione"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    elemento_grezzo_id: Mapped[int | None] = mapped_column(
        ForeignKey("elemento_grezzo.id", ondelete="CASCADE")
    )
    media_id: Mapped[int | None] = mapped_column(ForeignKey("media.id", ondelete="CASCADE"))
    tipo: Mapped[str] = mapped_column(String(30))
    testo: Mapped[str] = mapped_column(Text, default="")
    tempo_inizio_ms: Mapped[int | None] = mapped_column(Integer)
    tempo_fine_ms: Mapped[int | None] = mapped_column(Integer)
    modello: Mapped[str] = mapped_column(String(80), default="")
    versione_modello: Mapped[str] = mapped_column(String(40), default="")
    metadati: Mapped[dict[str, Any]] = mapped_column(default=dict)
    creato_il: Mapped[datetime] = mapped_column(TS, default=utcnow)


class Entita(Base):
    __tablename__ = "entita"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tipo: Mapped[str] = mapped_column(String(30))
    valore: Mapped[str] = mapped_column(Text)
    creato_il: Mapped[datetime] = mapped_column(TS, default=utcnow)
    __table_args__ = (UniqueConstraint("tipo", "valore", name="entita_tipo_valore"),)


class LegameEntita(Base):
    """Legame tra due entità (per esempio URL → dominio)."""

    __tablename__ = "legame_entita"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    da_entita_id: Mapped[int] = mapped_column(ForeignKey("entita.id", ondelete="CASCADE"), index=True)
    a_entita_id: Mapped[int] = mapped_column(ForeignKey("entita.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(40))
    evidenza: Mapped[dict[str, Any]] = mapped_column(default=dict)
    creato_il: Mapped[datetime] = mapped_column(TS, default=utcnow)
    __table_args__ = (UniqueConstraint("da_entita_id", "a_entita_id", "tipo", name="legame_unico"),)


class MenzioneEntita(Base):
    """Dove un'entità è stata trovata: elemento grezzo ed eventuale estrazione."""

    __tablename__ = "menzione_entita"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    entita_id: Mapped[int] = mapped_column(ForeignKey("entita.id", ondelete="CASCADE"), index=True)
    elemento_grezzo_id: Mapped[int] = mapped_column(
        ForeignKey("elemento_grezzo.id", ondelete="CASCADE"), index=True
    )
    estrazione_id: Mapped[int | None] = mapped_column(ForeignKey("estrazione.id", ondelete="CASCADE"))
    creato_il: Mapped[datetime] = mapped_column(TS, default=utcnow)
    __table_args__ = (
        UniqueConstraint("entita_id", "elemento_grezzo_id", "estrazione_id", name="menzione_unica"),
    )


class Sito(Base):
    __tablename__ = "sito"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    dominio: Mapped[str] = mapped_column(String(255), unique=True)
    gruppo: Mapped[int | None] = mapped_column(Integer, index=True)
    # Sintesi del confronto con gli elenchi ADM, ricalcolata a ogni confronto.
    esito_adm: Mapped[str] = mapped_column(String(30), default="non_determinabile", index=True)
    fonte_scoperta: Mapped[str | None] = mapped_column(String(40))
    primo_avvistamento: Mapped[datetime] = mapped_column(TS, default=utcnow)
    ultimo_snapshot_il: Mapped[datetime | None] = mapped_column(TS)
    creato_il: Mapped[datetime] = mapped_column(TS, default=utcnow)
    snapshot: Mapped[list[Snapshot]] = relationship(
        back_populates="sito", order_by="Snapshot.raccolto_il.desc()"
    )


class Snapshot(Base):
    __tablename__ = "snapshot"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sito_id: Mapped[int] = mapped_column(ForeignKey("sito.id", ondelete="CASCADE"), index=True)
    lavoro_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    stato: Mapped[str] = mapped_column(String(20))
    motivo: Mapped[str | None] = mapped_column(String(60))
    errore: Mapped[str | None] = mapped_column(Text)
    url_richiesto: Mapped[str] = mapped_column(Text)
    url_finale: Mapped[str | None] = mapped_column(Text)
    dominio_finale: Mapped[str | None] = mapped_column(String(255))
    codice_http: Mapped[int | None] = mapped_column(Integer)
    titolo: Mapped[str | None] = mapped_column(Text)
    reindirizzamenti: Mapped[list[Any]] = mapped_column(default=list)
    html_sha256: Mapped[str | None] = mapped_column(String(64))
    html_chiave: Mapped[str | None] = mapped_column(String(200))
    schermata_sha256: Mapped[str | None] = mapped_column(String(64))
    schermata_chiave: Mapped[str | None] = mapped_column(String(200))
    traffico_sha256: Mapped[str | None] = mapped_column(String(64))
    traffico_chiave: Mapped[str | None] = mapped_column(String(200))
    sha256: Mapped[str] = mapped_column(String(64))
    raccolto_il: Mapped[datetime] = mapped_column(TS, index=True)
    strumento: Mapped[str] = mapped_column(String(60), default="")
    versione_strumento: Mapped[str] = mapped_column(String(60), default="")
    metadati: Mapped[dict[str, Any]] = mapped_column(default=dict)
    sito: Mapped[Sito] = relationship(back_populates="snapshot")
    __table_args__ = (CheckConstraint("stato in ('riuscito','bloccato','errore')", name="snapshot_stato"),)


class Indicatore(Base):
    __tablename__ = "indicatore"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sito_id: Mapped[int] = mapped_column(ForeignKey("sito.id", ondelete="CASCADE"))
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("snapshot.id", ondelete="SET NULL"))
    codice: Mapped[str] = mapped_column(String(60))
    valore: Mapped[str] = mapped_column(String(20))
    evidenza: Mapped[dict[str, Any]] = mapped_column(default=dict)
    certezza: Mapped[float] = mapped_column(Numeric(4, 3), default=0)
    collettore: Mapped[str] = mapped_column(String(60))
    versione_collettore: Mapped[str] = mapped_column(String(20))
    rilevato_il: Mapped[datetime] = mapped_column(TS, default=utcnow)
    __table_args__ = (
        CheckConstraint("valore in ('presente','assente','non_determinabile')", name="indicatore_valore"),
        CheckConstraint("certezza >= 0 and certezza <= 1", name="indicatore_certezza"),
        Index("indicatore_sito_codice", "sito_id", "codice", "rilevato_il"),
    )


class Punteggio(Base):
    __tablename__ = "punteggio"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sito_id: Mapped[int] = mapped_column(ForeignKey("sito.id", ondelete="CASCADE"), index=True)
    ambito: Mapped[str] = mapped_column(String(80), default="piattaforma")
    vulnerabilita: Mapped[float | None] = mapped_column(Numeric(6, 2))
    livello_vulnerabilita: Mapped[str | None] = mapped_column(String(10))
    minaccia: Mapped[float | None] = mapped_column(Numeric(6, 2))
    livello_minaccia: Mapped[str | None] = mapped_column(String(10))
    trust_index: Mapped[float | None] = mapped_column(Numeric(6, 2))
    classe_rischio: Mapped[str | None] = mapped_column(String(10))
    copertura: Mapped[float] = mapped_column(Numeric(4, 3), default=0)
    versione_regole: Mapped[str] = mapped_column(String(40))
    dettaglio: Mapped[dict[str, Any]] = mapped_column(default=dict)
    calcolato_il: Mapped[datetime] = mapped_column(TS, default=utcnow)


class Revisione(Base):
    __tablename__ = "revisione"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tipo: Mapped[str] = mapped_column(String(30), index=True)
    stato: Mapped[str] = mapped_column(String(20), default="aperta", index=True)
    sito_id: Mapped[int | None] = mapped_column(ForeignKey("sito.id", ondelete="CASCADE"))
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("snapshot.id", ondelete="SET NULL"))
    elemento_grezzo_id: Mapped[int | None] = mapped_column(
        ForeignKey("elemento_grezzo.id", ondelete="SET NULL")
    )
    motivo: Mapped[str] = mapped_column(Text, default="")
    assegnata_a: Mapped[int | None] = mapped_column(ForeignKey("utente.id"))
    esito: Mapped[str | None] = mapped_column(String(40))
    giudizio: Mapped[dict[str, Any]] = mapped_column(default=dict)
    note: Mapped[str] = mapped_column(Text, default="")
    creata_il: Mapped[datetime] = mapped_column(TS, default=utcnow)
    chiusa_il: Mapped[datetime | None] = mapped_column(TS)
    chiusa_da: Mapped[int | None] = mapped_column(ForeignKey("utente.id"))
    sito: Mapped[Sito | None] = relationship()
    snapshot: Mapped[Snapshot | None] = relationship()
    assegnatario: Mapped[Utente | None] = relationship(foreign_keys=[assegnata_a])
    __table_args__ = (CheckConstraint("stato in ('aperta','in_carico','chiusa')", name="revisione_stato"),)


class Lavoro(Base):
    """Coda di lavoro. `coda` separa ciò che gira nei contenitori di raccolta dal resto."""

    __tablename__ = "lavoro"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    coda: Mapped[str] = mapped_column(String(20))
    tipo: Mapped[str] = mapped_column(String(40))
    carico: Mapped[dict[str, Any]] = mapped_column(default=dict)
    stato: Mapped[str] = mapped_column(String(20), default="in_attesa")
    tentativi: Mapped[int] = mapped_column(Integer, default=0)
    max_tentativi: Mapped[int] = mapped_column(Integer, default=3)
    disponibile_dal: Mapped[datetime] = mapped_column(TS, default=utcnow)
    preso_da: Mapped[str | None] = mapped_column(String(80))
    preso_il: Mapped[datetime | None] = mapped_column(TS)
    scade_il: Mapped[datetime | None] = mapped_column(TS)
    risultato: Mapped[dict[str, Any]] = mapped_column(default=dict)
    errore: Mapped[str | None] = mapped_column(Text)
    successivo: Mapped[str | None] = mapped_column(String(40))
    origine_id: Mapped[int | None] = mapped_column(BigInteger)
    sito_id: Mapped[int | None] = mapped_column(ForeignKey("sito.id", ondelete="SET NULL"), index=True)
    creato_da: Mapped[int | None] = mapped_column(ForeignKey("utente.id"))
    creato_il: Mapped[datetime] = mapped_column(TS, default=utcnow)
    chiuso_il: Mapped[datetime | None] = mapped_column(TS)
    sito: Mapped[Sito | None] = relationship()
    __table_args__ = (
        CheckConstraint("coda in ('raccolta','interna')", name="lavoro_coda"),
        CheckConstraint("stato in ('in_attesa','in_corso','completato','fallito')", name="lavoro_stato"),
        Index("lavoro_da_prendere", "coda", "stato", "disponibile_dal"),
    )


class AdmCaricamento(Base):
    __tablename__ = "adm_caricamento"
    id: Mapped[int] = mapped_column(primary_key=True)
    elenco: Mapped[str] = mapped_column(String(20))
    versione: Mapped[int] = mapped_column(Integer)
    stato: Mapped[str] = mapped_column(String(20), default="attivo")
    fonte_url: Mapped[str | None] = mapped_column(Text)
    nome_file: Mapped[str] = mapped_column(String(255), default="")
    sha256: Mapped[str] = mapped_column(String(64))
    elemento_grezzo_id: Mapped[int | None] = mapped_column(ForeignKey("elemento_grezzo.id"))
    righe_totali: Mapped[int] = mapped_column(Integer, default=0)
    righe_valide: Mapped[int] = mapped_column(Integer, default=0)
    righe_scartate: Mapped[int] = mapped_column(Integer, default=0)
    caricato_il: Mapped[datetime] = mapped_column(TS, default=utcnow)
    verificato_il: Mapped[datetime] = mapped_column(TS, default=utcnow)
    caricato_da: Mapped[int | None] = mapped_column(ForeignKey("utente.id"))
    note: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (
        UniqueConstraint("elenco", "versione", name="adm_caricamento_versione"),
        CheckConstraint("elenco in ('concessionari','siti_inibiti')", name="adm_elenco"),
        CheckConstraint("stato in ('attivo','sostituito')", name="adm_stato"),
    )


class AdmConcessionario(Base):
    __tablename__ = "adm_concessionario"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    caricamento_id: Mapped[int] = mapped_column(ForeignKey("adm_caricamento.id", ondelete="CASCADE"))
    numero_concessione: Mapped[str] = mapped_column(String(40), default="")
    ragione_sociale: Mapped[str] = mapped_column(Text, default="")
    dominio: Mapped[str] = mapped_column(String(255))
    dominio_registrabile: Mapped[str] = mapped_column(String(255))
    riga: Mapped[int] = mapped_column(Integer)
    riga_originale: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (
        Index("adm_conc_dominio", "caricamento_id", "dominio"),
        Index("adm_conc_registrabile", "caricamento_id", "dominio_registrabile"),
    )


class AdmSitoInibito(Base):
    __tablename__ = "adm_sito_inibito"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    caricamento_id: Mapped[int] = mapped_column(ForeignKey("adm_caricamento.id", ondelete="CASCADE"))
    dominio: Mapped[str] = mapped_column(String(255))
    dominio_registrabile: Mapped[str] = mapped_column(String(255))
    riga: Mapped[int] = mapped_column(Integer)
    riga_originale: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (
        Index("adm_inib_dominio", "caricamento_id", "dominio"),
        Index("adm_inib_registrabile", "caricamento_id", "dominio_registrabile"),
    )


class Puntata(Base):
    """Una puntata osservata su un sito o caricata dall'analista. Nessun dato sul giocatore."""

    __tablename__ = "puntata"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sito_id: Mapped[int] = mapped_column(ForeignKey("sito.id", ondelete="CASCADE"), index=True)
    tipo_gioco: Mapped[str | None] = mapped_column(String(40))
    importo_puntato: Mapped[float] = mapped_column(Numeric(14, 4))
    importo_vinto: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    valuta: Mapped[str] = mapped_column(String(10), default="EUR")
    momento: Mapped[datetime | None] = mapped_column(TS)
    fonte: Mapped[str] = mapped_column(String(20))
    elemento_grezzo_id: Mapped[int | None] = mapped_column(
        ForeignKey("elemento_grezzo.id", ondelete="SET NULL")
    )
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("snapshot.id", ondelete="SET NULL"))
    creato_il: Mapped[datetime] = mapped_column(TS, default=utcnow)
    __table_args__ = (CheckConstraint("fonte in ('osservata','caricata')", name="puntata_fonte"),)


class LegameSito(Base):
    """Segnale che due siti appartengono allo stesso operatore (domini gemelli)."""

    __tablename__ = "legame_sito"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sito_a: Mapped[int] = mapped_column(ForeignKey("sito.id", ondelete="CASCADE"), index=True)
    sito_b: Mapped[int] = mapped_column(ForeignKey("sito.id", ondelete="CASCADE"), index=True)
    motivo: Mapped[str] = mapped_column(String(40))
    valore: Mapped[str] = mapped_column(Text, default="")
    forza: Mapped[float] = mapped_column(Numeric(4, 3), default=1)
    creato_il: Mapped[datetime] = mapped_column(TS, default=utcnow)
    __table_args__ = (UniqueConstraint("sito_a", "sito_b", "motivo", "valore", name="legame_sito_unico"),)


class Canale(Base):
    """Canale o gruppo pubblico monitorato da una sonda. Nessun dato sui membri: solo il loro numero."""

    __tablename__ = "canale"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    piattaforma: Mapped[str] = mapped_column(String(20), default="telegram")
    identificativo: Mapped[str] = mapped_column(String(120))
    titolo: Mapped[str] = mapped_column(String(300), default="")
    tipo: Mapped[str | None] = mapped_column(String(20))
    stato: Mapped[str] = mapped_column(String(20), default="da_approvare", index=True)
    partecipanti: Mapped[int | None] = mapped_column(Integer)
    cursore: Mapped[int] = mapped_column(BigInteger, default=0)
    scoperto_da: Mapped[int | None] = mapped_column(ForeignKey("elemento_grezzo.id", ondelete="SET NULL"))
    motivo: Mapped[str] = mapped_column(Text, default="")
    ultimo_controllo: Mapped[datetime | None] = mapped_column(TS)
    ultimo_errore: Mapped[str | None] = mapped_column(Text)
    approvato_da: Mapped[int | None] = mapped_column(ForeignKey("utente.id"))
    creato_il: Mapped[datetime] = mapped_column(TS, default=utcnow)
    __table_args__ = (
        UniqueConstraint("piattaforma", "identificativo", name="canale_unico"),
        CheckConstraint(
            "stato in ('da_approvare','attivo','in_pausa','rifiutato','in_errore')", name="canale_stato"
        ),
    )


class ParolaChiave(Base):
    __tablename__ = "parola_chiave"
    id: Mapped[int] = mapped_column(primary_key=True)
    termine: Mapped[str] = mapped_column(String(120))
    categoria: Mapped[str] = mapped_column(String(40), default="gioco")
    lingua: Mapped[str] = mapped_column(String(10), default="it")
    attiva: Mapped[bool] = mapped_column(Boolean, default=True)
    avviso: Mapped[bool] = mapped_column(Boolean, default=False)
    creato_da: Mapped[int | None] = mapped_column(ForeignKey("utente.id"))
    creato_il: Mapped[datetime] = mapped_column(TS, default=utcnow)
    __table_args__ = (UniqueConstraint("termine", name="parola_chiave_unica"),)


class Avviso(Base):
    __tablename__ = "avviso"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tipo: Mapped[str] = mapped_column(String(40))
    titolo: Mapped[str] = mapped_column(String(300))
    testo: Mapped[str] = mapped_column(Text, default="")
    sito_id: Mapped[int | None] = mapped_column(ForeignKey("sito.id", ondelete="CASCADE"))
    elemento_grezzo_id: Mapped[int | None] = mapped_column(
        ForeignKey("elemento_grezzo.id", ondelete="CASCADE")
    )
    canale_id: Mapped[int | None] = mapped_column(ForeignKey("canale.id", ondelete="SET NULL"))
    letto: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    letto_da: Mapped[int | None] = mapped_column(ForeignKey("utente.id"))
    creato_il: Mapped[datetime] = mapped_column(TS, default=utcnow, index=True)


class Etichetta(Base):
    """Etichetta dell'analista su un elemento grezzo: forma il set di valutazione e di addestramento."""

    __tablename__ = "etichetta"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    elemento_grezzo_id: Mapped[int] = mapped_column(
        ForeignKey("elemento_grezzo.id", ondelete="CASCADE"), unique=True
    )
    pubblicita_gioco: Mapped[bool | None] = mapped_column(Boolean)
    entita: Mapped[dict[str, Any]] = mapped_column(default=dict)
    note: Mapped[str] = mapped_column(Text, default="")
    utente_id: Mapped[int | None] = mapped_column(ForeignKey("utente.id"))
    creato_il: Mapped[datetime] = mapped_column(TS, default=utcnow)
    aggiornato_il: Mapped[datetime] = mapped_column(TS, default=utcnow)


class EmojiSignificato(Base):
    """Dizionario delle emoji: significato nel contesto delle pubblicità di gioco, per piattaforma."""

    __tablename__ = "emoji"
    id: Mapped[int] = mapped_column(primary_key=True)
    carattere: Mapped[str] = mapped_column(String(16))
    piattaforma: Mapped[str] = mapped_column(String(20), default="")
    significato: Mapped[str] = mapped_column(String(200))
    categoria: Mapped[str] = mapped_column(String(40), default="")
    occorrenze: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint("carattere", "piattaforma", name="emoji_unica"),)


class Valutazione(Base):
    """Risultato di una valutazione sul set etichettato: precisione e richiamo misurati."""

    __tablename__ = "valutazione"
    id: Mapped[int] = mapped_column(primary_key=True)
    ambito: Mapped[str] = mapped_column(String(40))
    versione: Mapped[str] = mapped_column(String(80))
    esempi: Mapped[int] = mapped_column(Integer)
    misure: Mapped[dict[str, Any]] = mapped_column(default=dict)
    errori: Mapped[list[Any]] = mapped_column(default=list)
    eseguita_il: Mapped[datetime] = mapped_column(TS, default=utcnow)


class Modello(Base):
    """Modello addestrato o risultato non supervisionato (classificatore, argomenti), archiviato per hash."""

    __tablename__ = "modello"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(40), index=True)
    versione: Mapped[str] = mapped_column(String(80))
    chiave: Mapped[str | None] = mapped_column(String(200))
    metriche: Mapped[dict[str, Any]] = mapped_column(default=dict)
    attivo: Mapped[bool] = mapped_column(Boolean, default=True)
    addestrato_il: Mapped[datetime] = mapped_column(TS, default=utcnow)
    addestrato_da: Mapped[int | None] = mapped_column(ForeignKey("utente.id"))
