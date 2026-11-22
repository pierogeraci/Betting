"""Sonda Telegram: legge i canali e i gruppi pubblici indicati dall'analista.

Regole:
- solo canali e gruppi pubblici (con nome utente); un link d'invito o un gruppo privato si scarta;
- del messaggio restano testo, data, canale, link e media; mittente e autore non si leggono;
- un inoltro si registra solo se arriva da un canale, mai da una persona;
- quando Telegram chiede di attendere, si attende o ci si ferma e lo si riferisce;
- i file si scaricano solo se il messaggio supera il prefiltro (parole chiave o link).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.collect_client import CollectClient, CollectJob

SESSION = Path(os.environ.get("TELEGRAM_SESSIONE", "/sessione/sonda"))
# Attese brevi chieste dal servizio: Telethon attende da solo. Oltre questa soglia la sonda si ferma.
FLOOD_SLEEP = 120
URL_IN_TEXT = re.compile(r"(?i)\b(?:https?://|www\.|t\.me/)\S+")


def forget_entities(client: Any) -> None:
    """La sessione di Telethon salverebbe ogni entità incontrata, mittenti dei gruppi compresi.

    Si disattiva il salvataggio e si svuota ciò che una versione precedente avesse salvato.
    """
    client.session.save_entities = False
    try:
        client.session._conn.execute("delete from entities")  # noqa: SLF001 - tabella interna della sessione SQLite
        client.session._conn.commit()  # noqa: SLF001
    except Exception:  # noqa: BLE001, S110 - sessione nuova o di altro tipo: niente da svuotare
        pass


def prefilter(text: str, links: list[str], words: list[str]) -> bool:
    if links or URL_IN_TEXT.search(text or ""):
        return True
    low = (text or "").lower()
    return any(w.lower() in low for w in words)


def message_links(message: Any) -> list[str]:
    """Link nascosti dietro il testo e nei pulsanti: spesso il sito pubblicizzato è lì."""
    from telethon.tl import types

    links: list[str] = []
    for entity in message.entities or []:
        if isinstance(entity, types.MessageEntityTextUrl):
            links.append(entity.url)
    markup = getattr(message, "reply_markup", None)
    for row in getattr(markup, "rows", None) or []:
        for button in row.buttons:
            if getattr(button, "url", None):
                links.append(button.url)
    return list(dict.fromkeys(links))[:50]


def forwarded_channel(message: Any) -> int | None:
    from telethon.tl import types

    fwd = getattr(message, "fwd_from", None)
    if fwd is not None and isinstance(getattr(fwd, "from_id", None), types.PeerChannel):
        return fwd.from_id.channel_id
    return None


def media_kind(message: Any) -> str | None:
    if message.photo:
        return "immagine"
    if message.video or message.gif:
        return "video"
    if message.voice or message.audio:
        return "audio"
    if message.document:
        return "documento"
    return None


async def collect(payload: dict[str, Any], client: Any, upload) -> dict[str, Any]:
    from telethon import errors
    from telethon.tl import types

    result: dict[str, Any] = {"messaggi": [], "cursori": {}, "canali": {}, "attesa": 0, "errori": []}
    words = payload.get("parole", [])
    limit = int(payload.get("messaggi_per_canale", 200))
    max_bytes = int(payload.get("max_media_mb", 25)) * 1024 * 1024
    for channel in payload.get("canali", []):
        cid = str(channel["id"])
        try:
            entity = await client.get_entity(channel["nome"])
        except errors.FloodWaitError as exc:
            result["attesa"] = exc.seconds
            break
        except (ValueError, errors.RPCError) as exc:
            result["canali"][cid] = {"errore": f"Canale non raggiungibile: {type(exc).__name__}"}
            continue
        if not isinstance(entity, types.Channel) or not getattr(entity, "username", None):
            result["canali"][cid] = {"errore": "Non è un canale o gruppo pubblico: escluso"}
            continue
        result["canali"][cid] = {
            "titolo": (entity.title or "")[:300],
            "tipo": "canale" if entity.broadcast else "gruppo",
            "partecipanti": getattr(entity, "participants_count", None),
            "nome": entity.username.lower(),
        }
        cursor = int(channel.get("cursore") or 0)
        try:
            async for message in client.iter_messages(entity, min_id=cursor, limit=limit, reverse=True):
                cursor = max(cursor, message.id)
                if isinstance(message, types.MessageService):
                    continue  # ingressi, uscite e altre azioni: nessun contenuto, nessun dato da conservare
                text = message.message or ""
                links = message_links(message)
                item = {
                    "canale_id": channel["id"],
                    "canale": entity.username.lower(),
                    "id": message.id,
                    "data": message.date.astimezone(UTC).isoformat() if message.date else None,
                    "testo": text[:20000],
                    "link": links,
                    "inoltrato_da_canale": forwarded_channel(message),
                    "visualizzazioni": getattr(message, "views", None),
                    "media": [],
                }
                kind = media_kind(message)
                if kind and payload.get("scarica_media") and prefilter(text, links, words):
                    size = getattr(message.file, "size", 0) or 0
                    if 0 < size <= max_bytes:
                        data = await client.download_media(message, file=bytes)
                        if data:
                            name = f"m_{channel['id']}_{message.id}{message.file.ext or ''}"
                            upload(name, data)
                            item["media"].append(
                                {
                                    "nome": name,
                                    "sha256": hashlib.sha256(data).hexdigest(),
                                    "tipo": kind,
                                    "mime": message.file.mime_type or "",
                                    "dimensione": len(data),
                                }
                            )
                    elif size > max_bytes:
                        item["media_saltato"] = f"File di {size // 1_048_576} MB oltre il limite"
                elif kind:
                    item["media_non_scaricato"] = kind
                result["messaggi"].append(item)
        except errors.FloodWaitError as exc:
            result["attesa"] = exc.seconds
            result["cursori"][cid] = cursor
            break
        except errors.RPCError as exc:
            result["canali"][cid]["errore"] = f"Lettura interrotta: {type(exc).__name__}"
        result["cursori"][cid] = cursor
    return result


async def _run(payload: dict[str, Any], upload) -> dict[str, Any]:
    from telethon import TelegramClient

    api_id, api_hash = os.environ.get("TELEGRAM_API_ID"), os.environ.get("TELEGRAM_API_HASH")
    if not api_id or not api_hash:
        raise RuntimeError("TELEGRAM_API_ID e TELEGRAM_API_HASH mancano in .env")
    client = TelegramClient(str(SESSION), int(api_id), api_hash, flood_sleep_threshold=FLOOD_SLEEP)
    forget_entities(client)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError("Account non collegato: esegui make telegram-login")
        return await collect(payload, client, upload)
    finally:
        await client.disconnect()


def run_job(client: CollectClient, job: CollectJob) -> dict[str, Any]:
    if os.environ.get("TELEGRAM_PROBE_ENABLED", "true").lower() in {"false", "0", "no"}:
        manifest = {
            "esito": "errore",
            "errori": ["Sonda Telegram spenta"],
            "messaggi": [],
            "cursori": {},
            "canali": {},
            "attesa": 0,
        }
    else:
        manifest = asyncio.run(_run(job.payload, lambda name, data: client.upload(job.id, name, data)))
        manifest["esito"] = "riuscito"
    manifest["raccolto_il"] = datetime.now(UTC).isoformat()
    client.upload(job.id, "manifesto.json", json.dumps(manifest).encode(), "application/json")
    return {"esito": manifest["esito"], "messaggi": len(manifest["messaggi"]), "attesa": manifest["attesa"]}
