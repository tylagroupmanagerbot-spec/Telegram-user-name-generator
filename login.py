# ============================================================
# File: login.py
# One-time Telegram authorization
# ============================================================

import os
import asyncio
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient


BASE_DIR = Path(__file__).resolve().parent
SESSION_DIR = BASE_DIR / "session"

SESSION_DIR.mkdir(
    parents=True,
    exist_ok=True
)

load_dotenv(BASE_DIR / ".env")


API_ID = os.getenv("API_ID", "").strip()
API_HASH = os.getenv("API_HASH", "").strip()


if not API_ID:
    raise RuntimeError("API_ID is missing from .env")

if not API_HASH:
    raise RuntimeError("API_HASH is missing from .env")


try:
    API_ID = int(API_ID)

except ValueError:
    raise RuntimeError("API_ID must be a number")


SESSION_FILE = SESSION_DIR / "personal_account"


async def main():

    print("=" * 55)
    print("TELEGRAM ACCOUNT LOGIN")
    print("=" * 55)

    print()
    print("This login runs only on this device.")
    print("Do not send your Telegram login code to anyone.")
    print()

    client = TelegramClient(
        str(SESSION_FILE),
        API_ID,
        API_HASH
    )

    try:

        await client.start()

        me = await client.get_me()

        print()
        print("=" * 55)
        print("LOGIN SUCCESSFUL")
        print("=" * 55)

        print(f"Telegram ID: {me.id}")

        if me.username:
            print(f"Username: @{me.username}")

        else:
            print("Username: None")

        print()
        print(
            "Session created:"
        )

        print(
            SESSION_FILE.with_suffix(".session")
        )

        print()
        print(
            "Keep this session file private."
        )

    finally:

        await client.disconnect()


if __name__ == "__main__":

    asyncio.run(main())
