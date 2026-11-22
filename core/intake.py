"""Inserimento manuale: un URL o un file caricato dall'analista entra nella pipeline."""

from __future__ import annotations

import mimetypes
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core import queue
from core.domains import NormalizedUrl, normalize_url  # noqa: F401 - riesportata
from core.models import ElementoGrezzo, Entita, Lavoro, LegameEntita, Media, MenzioneEntita, Sito, Sonda
from core.storage import archive_bytes, sha256_hex

MANUAL = "manuale"
# Da dove arriva un file caricato a mano. "telegram" lo esclude da ogni addestramento.
PROVENANCES = {"telegram", "wechat", "facebook", "instagram", "vk", "sito", "app", "altro"}


@dataclass
class UrlSubmission:
    url: NormalizedUrl
    site: Sito
    element: ElementoGrezzo
    job: Lavoro
    already_known: bool


def get_or_create_entity(session: Session, kind: str, value: str) -> Entita:
    session.execute(insert(Entita).values(tipo=kind, valore=value).on_conflict_do_nothing())
    return session.execute(select(Entita).where(Entita.tipo == kind, Entita.valore == value)).scalar_one()


def link_entities(session: Session, source: Entita, target: Entita, kind: str) -> None:
    session.execute(
        insert(LegameEntita)
        .values(da_entita_id=source.id, a_entita_id=target.id, tipo=kind, evidenza={})
        .on_conflict_do_nothing()
    )


def mention(session: Session, entity: Entita, element: ElementoGrezzo) -> None:
    exists = session.execute(
        select(MenzioneEntita.id).where(
            MenzioneEntita.entita_id == entity.id,
            MenzioneEntita.elemento_grezzo_id == element.id,
            MenzioneEntita.estrazione_id.is_(None),
        )
    ).first()
    if not exists:
        session.add(MenzioneEntita(entita_id=entity.id, elemento_grezzo_id=element.id))


def get_or_create_site(session: Session, domain: str) -> Sito:
    session.execute(insert(Sito).values(dominio=domain).on_conflict_do_nothing())
    return session.execute(select(Sito).where(Sito.dominio == domain)).scalar_one()


def _probe_id(session: Session, name: str) -> int | None:
    return session.execute(select(Sonda.id).where(Sonda.nome == name)).scalar_one_or_none()


def register_url(session: Session, element: ElementoGrezzo, url: NormalizedUrl) -> Sito:
    """Crea entità e sito per un URL trovato in un elemento grezzo. Usata da ogni fonte."""
    url_entity = get_or_create_entity(session, "url", url.url)
    domain_entity = get_or_create_entity(session, "dominio", url.registrable)
    link_entities(session, url_entity, domain_entity, "appartiene_a")
    mention(session, url_entity, element)
    mention(session, domain_entity, element)
    return get_or_create_site(session, url.registrable)


def request_snapshot(
    session: Session, site: Sito, url: str, user_id: int | None = None, secondary: bool = False
) -> Lavoro:
    """Mette in coda lo snapshot di una sola pagina; per la pagina principale anche il confronto ADM."""
    if not secondary:
        queue.enqueue(
            session,
            queue=queue.INTERNAL,
            kind="confronto_adm",
            payload={"sito_id": site.id},
            site_id=site.id,
            user_id=user_id,
        )
    return queue.enqueue(
        session,
        queue=queue.COLLECT,
        kind="snapshot",
        payload={"url": url, "sito_id": site.id, "secondaria": secondary},
        next_kind="acquisisci_snapshot",
        site_id=site.id,
        user_id=user_id,
        max_attempts=2,
    )


def submit_url(session: Session, raw_url: str, user_id: int | None = None) -> UrlSubmission:
    """Registra un URL inserito a mano. Solleva InvalidUrl se non è accettabile."""
    url = normalize_url(raw_url)
    digest = sha256_hex(url.url.encode())
    element = session.execute(
        select(ElementoGrezzo).where(ElementoGrezzo.fonte == MANUAL, ElementoGrezzo.sha256 == digest)
    ).scalar_one_or_none()
    known = element is not None
    if element is None:
        element = ElementoGrezzo(
            sonda_id=_probe_id(session, MANUAL),
            fonte=MANUAL,
            tipo="url",
            riferimento=url.url,
            contenuto=url.url,
            sha256=digest,
            inserito_da=user_id,
            metadati={"testo_inserito": raw_url.strip()[:2000], "schema_assunto": url.scheme_assumed},
        )
        session.add(element)
        session.flush()
    site = register_url(session, element, url)
    job = request_snapshot(session, site, url.url, user_id)
    return UrlSubmission(url=url, site=site, element=element, job=job, already_known=known)


_MEDIA_KINDS = {"image": "immagine", "video": "video", "audio": "audio"}


def media_kind(filename: str, mime: str) -> str:
    if filename.lower().endswith(".apk") or mime == "application/vnd.android.package-archive":
        return "apk"
    return _MEDIA_KINDS.get(mime.split("/")[0], "documento")


def safe_filename(name: str) -> str:
    name = re.sub(r"[^\w.\- ]+", "_", (name or "file").replace("\\", "/").split("/")[-1]).strip(" .")
    return (name or "file")[:200]


@dataclass
class FileSubmission:
    element: ElementoGrezzo
    media: Media
    already_known: bool


def submit_file(
    session: Session,
    filename: str,
    data: bytes,
    user_id: int | None = None,
    note: str = "",
    provenance: str = "",
) -> FileSubmission:
    """Archivia un file caricato dall'analista. Il file non viene mai aperto né eseguito qui."""
    if not data:
        raise ValueError("Il file è vuoto.")
    name = safe_filename(filename)
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    digest, key = archive_bytes(data, mime)
    element = session.execute(
        select(ElementoGrezzo).where(ElementoGrezzo.fonte == MANUAL, ElementoGrezzo.sha256 == digest)
    ).scalar_one_or_none()
    if element is not None:
        return FileSubmission(element=element, media=element.media[0], already_known=True)
    element = ElementoGrezzo(
        sonda_id=_probe_id(session, MANUAL),
        fonte=MANUAL,
        tipo="file",
        riferimento=name,
        oggetto_chiave=key,
        sha256=digest,
        inserito_da=user_id,
        metadati={
            "nota": note.strip()[:2000],
            "provenienza": provenance if provenance in PROVENANCES else "altro",
        },
    )
    session.add(element)
    session.flush()
    media = Media(
        elemento_grezzo_id=element.id,
        tipo=media_kind(name, mime),
        mime=mime,
        nome_file=name,
        dimensione=len(data),
        sha256=digest,
        oggetto_chiave=key,
    )
    session.add(media)
    session.flush()
    from core.media_jobs import request_extraction

    if media.tipo in {"immagine", "video", "audio"}:
        request_extraction(session, media, user_id=user_id)
    elif media.tipo == "apk":
        from core.apk import request_apk_analysis

        request_apk_analysis(session, media, user_id=user_id)
    return FileSubmission(element=element, media=media, already_known=False)
