"""Acquisizione di ciò che i contenitori di raccolta lasciano nel secchio di arrivo.

Il contenuto arriva da un contenitore che ha letto pagine ostili: non ci si fida
del manifesto. Gli hash si ricalcolano qui e i campi si validano uno per uno.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from core import adm
from core.config import get_settings
from core.domains import InvalidUrl, normalize_host
from core.models import Lavoro, Revisione, Sito, Snapshot, utcnow
from core.storage import archive_bytes, get_store, sha256_hex

MAX_MANIFEST = 2_000_000
FILES = {"html": "text/html", "schermata": "image/png", "traffico": "application/json"}
STATES = {"riuscito", "bloccato", "errore"}


class IngestError(Exception):
    pass


def _text(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    return str(value)[:limit]


def _read_manifest(job_id: int) -> dict[str, Any]:
    store = get_store()
    bucket = get_settings().s3_inbox_bucket
    try:
        raw = store.get(bucket, f"{job_id}/manifesto.json")
    except FileNotFoundError as exc:
        raise IngestError("Manifesto mancante nel secchio di arrivo") from exc
    if len(raw) > MAX_MANIFEST:
        raise IngestError("Manifesto troppo grande")
    try:
        manifest = json.loads(raw)
    except ValueError as exc:
        raise IngestError("Manifesto non leggibile") from exc
    if not isinstance(manifest, dict):
        raise IngestError("Manifesto non valido")
    return manifest


def _take_file(job_id: int, entry: Any, content_type: str) -> tuple[str, str] | None:
    """Legge un file dal secchio di arrivo, ne verifica l'hash e lo sposta nell'archivio."""
    if not isinstance(entry, dict) or not entry.get("nome"):
        return None
    name = str(entry["nome"])
    if "/" in name or ".." in name:
        raise IngestError("Nome di file non valido nel manifesto")
    store = get_store()
    bucket = get_settings().s3_inbox_bucket
    data = store.get(bucket, f"{job_id}/{name}")
    digest = sha256_hex(data)
    if entry.get("sha256") and entry["sha256"] != digest:
        raise IngestError(f"Hash non corrispondente per {name}")
    _, key = archive_bytes(data, content_type)
    return digest, key


def _cleanup(job_id: int, manifest: dict[str, Any]) -> None:
    store = get_store()
    bucket = get_settings().s3_inbox_bucket
    for entry in (manifest.get("file") or {}).values():
        if isinstance(entry, dict) and entry.get("nome"):
            store.delete(bucket, f"{job_id}/{entry['nome']}")
    store.delete(bucket, f"{job_id}/manifesto.json")


def _final_host(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return normalize_host(urlsplit(url).hostname or "")
    except InvalidUrl:
        return None


def ingest_snapshot(session: Session, origin: Lavoro) -> Snapshot:
    """Trasforma il risultato di un lavoro `snapshot` in una riga di `snapshot` con le sue prove."""
    site = session.get(Sito, origin.sito_id) if origin.sito_id else None
    if site is None:
        raise IngestError("Il lavoro non è collegato a un sito")
    manifest = _read_manifest(origin.id)
    state = manifest.get("esito")
    if state not in STATES:
        raise IngestError("Esito sconosciuto nel manifesto")
    files = manifest.get("file") if isinstance(manifest.get("file"), dict) else {}
    stored = {name: _take_file(origin.id, files.get(name), ctype) for name, ctype in FILES.items()}
    try:
        collected = datetime.fromisoformat(str(manifest.get("raccolto_il")))
        if collected.tzinfo is None:
            raise ValueError
    except ValueError:
        collected = utcnow()
    chain = manifest.get("reindirizzamenti") if isinstance(manifest.get("reindirizzamenti"), list) else []
    chain = [
        {
            "url": _text(step.get("url"), 2000),
            "codice": step.get("codice") if isinstance(step.get("codice"), int) else None,
        }
        for step in chain[:20]
        if isinstance(step, dict)
    ]
    final_url = _text(manifest.get("url_finale"), 2000)
    intercepted = bool(manifest.get("rete_intercettata"))
    proof = {
        "esito": state,
        "url_richiesto": origin.carico.get("url"),
        "url_finale": final_url,
        "raccolto_il": collected.isoformat(),
        "file": {k: v[0] for k, v in stored.items() if v},
    }
    snapshot = Snapshot(
        sito_id=site.id,
        lavoro_id=origin.id,
        stato=state,
        motivo=_text(manifest.get("motivo"), 60),
        errore=_text(manifest.get("errore"), 2000),
        url_richiesto=str(origin.carico.get("url", ""))[:2000],
        url_finale=final_url,
        dominio_finale=_final_host(final_url),
        codice_http=manifest.get("codice_http") if isinstance(manifest.get("codice_http"), int) else None,
        titolo=_text(manifest.get("titolo"), 500),
        reindirizzamenti=chain,
        html_sha256=stored["html"][0] if stored["html"] else None,
        html_chiave=stored["html"][1] if stored["html"] else None,
        schermata_sha256=stored["schermata"][0] if stored["schermata"] else None,
        schermata_chiave=stored["schermata"][1] if stored["schermata"] else None,
        traffico_sha256=stored["traffico"][0] if stored["traffico"] else None,
        traffico_chiave=stored["traffico"][1] if stored["traffico"] else None,
        sha256=sha256_hex(json.dumps(proof, sort_keys=True).encode()),
        raccolto_il=collected,
        strumento=_text(manifest.get("strumento"), 60) or "",
        versione_strumento=_text(manifest.get("versione_strumento"), 60) or "",
        metadati={
            "user_agent": _text(manifest.get("user_agent"), 300),
            "rete_intercettata": intercepted,
            "html_troncato": bool(manifest.get("html_troncato")),
            "estratto_blocco": _text(manifest.get("estratto_blocco"), 300),
            "durata_ms": manifest.get("durata_ms") if isinstance(manifest.get("durata_ms"), int) else None,
            "richieste_bloccate": manifest.get("richieste_bloccate")
            if isinstance(manifest.get("richieste_bloccate"), int)
            else 0,
        },
    )
    session.add(snapshot)
    site.ultimo_snapshot_il = collected
    session.flush()
    if state == "bloccato":
        session.add(
            Revisione(
                tipo="pagina_bloccata",
                sito_id=site.id,
                snapshot_id=snapshot.id,
                motivo=f"{snapshot.motivo or 'blocco'}: la pagina non è stata letta. Nessun tentativo di aggiramento.",
            )
        )
    adm.compare_site(session, site, snapshot.id)
    session.flush()
    _cleanup(origin.id, manifest)
    return snapshot


def ingest_adm(session: Session, origin: Lavoro) -> dict[str, Any]:
    """Carica un elenco ADM scaricato dal contenitore di raccolta."""
    manifest = _read_manifest(origin.id)
    kind = origin.carico.get("elenco")
    if manifest.get("esito") != "riuscito":
        raise IngestError(f"Scaricamento non riuscito: {_text(manifest.get('errore'), 300)}")
    entry = (manifest.get("file") or {}).get("elenco")
    if not isinstance(entry, dict) or not entry.get("nome"):
        raise IngestError("File dell'elenco mancante")
    store = get_store()
    data = store.get(get_settings().s3_inbox_bucket, f"{origin.id}/{entry['nome']}")
    if entry.get("sha256") != sha256_hex(data):
        raise IngestError("Hash dell'elenco non corrispondente")
    load, created = adm.load_list(
        session,
        kind,
        data,
        filename=str(entry["nome"]),
        source_url=_text(manifest.get("url_finale") or origin.carico.get("url"), 2000),
        user_id=origin.creato_da,
    )
    _cleanup(origin.id, manifest)
    return {
        "caricamento_id": load.id,
        "versione": load.versione,
        "nuovo": created,
        "righe_valide": load.righe_valide,
    }
