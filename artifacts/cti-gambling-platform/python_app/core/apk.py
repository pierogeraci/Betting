"""Analisi delle app Android (Fase 4): accodamento e acquisizione."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from core import discovery, queue
from core.config import get_settings
from core.ingest import IngestError, _read_manifest
from core.intake import get_or_create_entity, mention
from core.models import Estrazione, Lavoro, Media
from core.storage import get_store, read_archive


def _copy_to_work(media: Media) -> None:
    settings = get_settings()
    store = get_store()
    if not store.exists(settings.s3_work_bucket, media.sha256):
        store.put(
            settings.s3_work_bucket,
            media.sha256,
            read_archive(media.oggetto_chiave),
            "application/vnd.android.package-archive",
        )


def request_apk_analysis(
    session: Session, media: Media, user_id: int | None = None, dynamic: bool = False
) -> Lavoro | None:
    """Copia l'APK nel secchio di lavorazione e accoda l'analisi nel contenitore isolato delle app."""
    kind = "apk_dinamica" if dynamic else "apk"
    pending = session.execute(
        select(Lavoro.id).where(
            Lavoro.tipo == kind,
            Lavoro.carico["media_id"].astext == str(media.id),
            Lavoro.stato.in_(["in_attesa", "in_corso"]),
        )
    ).first()
    if pending:
        return None
    _copy_to_work(media)
    payload: dict[str, Any] = {"media_id": media.id, "chiave": media.sha256}
    if dynamic:
        static = session.execute(
            select(Estrazione)
            .where(Estrazione.media_id == media.id, Estrazione.tipo == "apk")
            .order_by(Estrazione.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if static is None or not static.metadati.get("pacchetto"):
            return None  # serve prima l'analisi statica, che dà il nome del pacchetto
        payload["pacchetto"] = static.metadati["pacchetto"]
    return queue.enqueue(
        session,
        queue=queue.COLLECT,
        kind=kind,
        payload=payload,
        next_kind="acquisisci_apk",
        user_id=user_id,
        max_attempts=1,
    )


def ingest_apk(session: Session, origin: Lavoro) -> dict[str, Any]:
    manifest = _read_manifest(origin.id)
    media = session.get(Media, int(origin.carico.get("media_id") or 0))
    if media is None:
        raise IngestError("APK di origine non trovato")
    store, settings = get_store(), get_settings()
    store.delete(settings.s3_inbox_bucket, f"{origin.id}/manifesto.json")
    if manifest.get("esito") != "riuscito":
        session.add(
            Estrazione(
                elemento_grezzo_id=media.elemento_grezzo_id,
                media_id=media.id,
                tipo="apk_errore",
                testo=str(manifest.get("errore") or manifest.get("errori"))[:2000],
                modello=origin.tipo,
            )
        )
        return {"esito": "errore"}
    stats = discovery.RunStats()
    element = media.elemento
    if origin.tipo == "apk":
        info = manifest.get("apk") if isinstance(manifest.get("apk"), dict) else {}
        clean = {
            k: info.get(k)
            for k in (
                "pacchetto",
                "nome_app",
                "versione",
                "sdk_minimo",
                "sdk_target",
                "sha256_apk",
                "permessi_pericolosi",
                "permessi_totali",
                "librerie_pubblicitarie",
                "tracker",
                "domini",
                "domini_candidati",
                "url",
                "certificato",
                "attivita",
                "servizi",
                "punteggio_sicurezza",
            )
        }
        session.add(
            Estrazione(
                elemento_grezzo_id=media.elemento_grezzo_id,
                media_id=media.id,
                tipo="apk",
                testo=f"{clean.get('nome_app') or ''} {clean.get('pacchetto') or ''}".strip(),
                modello="MobSF",
                metadati=clean,
            )
        )
        if clean.get("pacchetto"):
            mention(
                session, get_or_create_entity(session, "app_android", str(clean["pacchetto"])[:200]), element
            )
        cert = (clean.get("certificato") or {}).get("sha256")
        if cert:
            mention(session, get_or_create_entity(session, "certificato_apk", cert), element)
        domains = [str(d)[:255] for d in (clean.get("domini_candidati") or [])][:50]
    else:
        traffic = manifest.get("traffico") if isinstance(manifest.get("traffico"), dict) else {}
        session.add(
            Estrazione(
                elemento_grezzo_id=media.elemento_grezzo_id,
                media_id=media.id,
                tipo="apk_traffico",
                testo="",
                modello="emulatore+mitmproxy",
                metadati={"traffico": traffic, "durata_s": manifest.get("durata_s")},
            )
        )
        domains = [
            str(d.get("host", ""))[:255] for d in (traffic.get("domini") or [])[:100] if isinstance(d, dict)
        ]
    from probes.apk.static import SDK_DOMAINS, registrable

    candidates = sorted({registrable(d) for d in domains if d and registrable(d) not in SDK_DOMAINS})
    # Domini trovati in un'app di gioco caricata dall'analista: entrano nella lista URL, entro un tetto.
    discovery.process_text(
        session,
        element,
        "",
        stats,
        keywords=[],
        source_label="apk",
        max_new_sites=15,
        extra_urls=[f"https://{d}/" for d in candidates],
        require_keyword=False,
    )
    session.flush()
    return {"domini": len(candidates), "siti_nuovi": stats.new_sites}
