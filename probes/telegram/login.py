"""Primo accesso dell'account Telegram dedicato. Lo esegue l'utente: chiede il numero e il codice."""

import asyncio
import os

from probes.telegram.probe import SESSION


async def main() -> None:
    from telethon import TelegramClient

    SESSION.parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(SESSION), int(os.environ["TELEGRAM_API_ID"]), os.environ["TELEGRAM_API_HASH"])
    await client.start()
    me = await client.get_me()
    print(f"Account collegato (id {me.id}). La sessione resta nel volume della sonda, fuori dal repository.")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
