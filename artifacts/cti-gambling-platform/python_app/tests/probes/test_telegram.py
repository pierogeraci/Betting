"""Sonda Telegram con un client finto: nessuna rete, oggetti Telethon veri."""

import asyncio
from datetime import UTC, datetime

from telethon import errors
from telethon.tl import types

from probes.telegram.probe import collect, prefilter


class FakeFile:
    def __init__(self, size, ext=".jpg", mime="image/jpeg"):
        self.size, self.ext, self.mime_type = size, ext, mime


class FakeMessage:
    def __init__(
        self, mid, text, *, entities=None, fwd=None, photo=False, size=1000, sender="mittente-segreto-42"
    ):
        self.id, self.message, self.entities, self.fwd_from = mid, text, entities or [], fwd
        self.date = datetime(2026, 11, 20, 10, mid % 60, tzinfo=UTC)
        self.photo, self.video, self.gif, self.voice, self.audio, self.document = (
            photo,
            False,
            False,
            False,
            False,
            False,
        )
        self.file = FakeFile(size) if photo else None
        self.reply_markup = None
        self.views = 120
        self.sender = sender  # la sonda non deve mai leggerlo


class FakeClient:
    def __init__(self, entities, messages, flood_on=None):
        self.entities, self.messages, self.flood_on, self.downloaded = entities, messages, flood_on, []

    async def get_entity(self, name):
        if name == self.flood_on:
            raise errors.FloodWaitError(request=None, capture=42)
        if name not in self.entities:
            raise ValueError("non trovato")
        return self.entities[name]

    async def iter_messages(self, entity, min_id=0, limit=100, reverse=True):
        for m in self.messages.get(entity.username, []):
            if m.id > min_id:
                yield m

    async def download_media(self, message, file=bytes):
        self.downloaded.append(message.id)
        return b"\xff\xd8 immagine finta"


def channel(name, broadcast=True, username=True):
    return types.Channel(
        id=hash(name) % 10**9,
        title=name.title(),
        photo=types.ChatPhotoEmpty(),
        date=None,
        username=name if username else None,
        broadcast=broadcast,
        megagroup=not broadcast,
        participants_count=1500,
    )


def test_collect_public_channel_without_authors():
    msgs = {
        "scommesse_vip": [
            FakeMessage(5, "vecchio"),
            FakeMessage(11, "🎰 Bonus 200% su vincitutto-bet.com", photo=True),
            FakeMessage(
                12,
                "Iscriviti qui",
                entities=[
                    types.MessageEntityTextUrl(offset=0, length=8, url="https://nascosto-casino.net/r")
                ],
            ),
            FakeMessage(
                13,
                "Inoltrato",
                fwd=types.MessageFwdHeader(date=datetime.now(UTC), from_id=types.PeerChannel(777)),
            ),
            FakeMessage(
                14,
                "Inoltrato da persona",
                fwd=types.MessageFwdHeader(date=datetime.now(UTC), from_id=types.PeerUser(888)),
            ),
            FakeMessage(15, "foto senza nulla di rilevante", photo=True),
        ]
    }
    client = FakeClient({"scommesse_vip": channel("scommesse_vip")}, msgs)
    uploads = {}
    payload = {
        "canali": [{"id": 1, "nome": "scommesse_vip", "cursore": 10}],
        "parole": ["bonus"],
        "scarica_media": True,
        "max_media_mb": 5,
    }
    result = asyncio.run(collect(payload, client, lambda n, d: uploads.setdefault(n, d)))
    ids = [m["id"] for m in result["messaggi"]]
    assert ids == [11, 12, 13, 14, 15]  # riprende dal cursore
    assert result["cursori"]["1"] == 15
    assert result["messaggi"][1]["link"] == ["https://nascosto-casino.net/r"]
    assert result["messaggi"][2]["inoltrato_da_canale"] == 777
    assert result["messaggi"][3]["inoltrato_da_canale"] is None  # una persona non si registra
    assert client.downloaded == [11]  # il prefiltro scarta la foto senza parole chiave né link
    assert result["messaggi"][4]["media_non_scaricato"] == "immagine"
    assert result["canali"]["1"]["partecipanti"] == 1500
    flat = str(result)
    assert "mittente-segreto-42" not in flat and "sender" not in flat


def test_private_or_user_entities_are_excluded():
    client = FakeClient(
        {
            "gruppo_privato": channel("gruppo_privato", username=False),
            "mario": types.User(id=1, username="mario"),
        },
        {},
    )
    payload = {
        "canali": [
            {"id": 1, "nome": "gruppo_privato"},
            {"id": 2, "nome": "mario"},
            {"id": 3, "nome": "sparito"},
        ],
        "parole": [],
    }
    result = asyncio.run(collect(payload, client, lambda n, d: None))
    assert "pubblico" in result["canali"]["1"]["errore"] and "pubblico" in result["canali"]["2"]["errore"]
    assert "non raggiungibile" in result["canali"]["3"]["errore"]
    assert result["messaggi"] == []


def test_flood_wait_stops_and_reports():
    client = FakeClient({"a": channel("a")}, {}, flood_on="a")
    result = asyncio.run(
        collect(
            {"canali": [{"id": 1, "nome": "a"}, {"id": 2, "nome": "b"}], "parole": []},
            client,
            lambda n, d: None,
        )
    )
    assert result["attesa"] == 42 and "2" not in result["canali"]


def test_media_size_limit():
    msgs = {"c": [FakeMessage(1, "bonus", photo=True, size=50 * 1024 * 1024)]}
    client = FakeClient({"c": channel("c")}, msgs)
    result = asyncio.run(
        collect(
            {
                "canali": [{"id": 1, "nome": "c"}],
                "parole": ["bonus"],
                "scarica_media": True,
                "max_media_mb": 5,
            },
            client,
            lambda n, d: None,
        )
    )
    assert client.downloaded == [] and "oltre il limite" in result["messaggi"][0]["media_saltato"]


def test_prefilter():
    assert prefilter("guarda t.me/qualcosa", [], [])
    assert prefilter("super BONUS", [], ["bonus"])
    assert not prefilter("buongiorno", [], ["bonus"])


def test_session_does_not_store_entities(tmp_path):
    from telethon import TelegramClient

    from probes.telegram.probe import forget_entities

    client = TelegramClient(str(tmp_path / "s"), 1, "x")
    client.session._conn.execute("insert into entities values (1, 2, 'mario', '+39000', 'Mario', 0)")
    forget_entities(client)
    assert client.session.save_entities is False
    assert client.session._conn.execute("select count(*) from entities").fetchone()[0] == 0


def test_service_messages_are_skipped():
    msgs = {
        "c": [
            types.MessageService(
                id=3,
                peer_id=types.PeerChannel(1),
                date=datetime.now(UTC),
                action=types.MessageActionChatJoinedByLink(inviter_id=5),
            ),
            FakeMessage(4, "testo"),
        ]
    }
    client = FakeClient({"c": channel("c")}, msgs)
    result = asyncio.run(
        collect({"canali": [{"id": 1, "nome": "c"}], "parole": []}, client, lambda n, d: None)
    )
    assert [m["id"] for m in result["messaggi"]] == [4] and result["cursori"]["1"] == 4
