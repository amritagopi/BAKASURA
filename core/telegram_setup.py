"""
One-time interactive login for the DEDICATED OSINT Telegram account used by
telegram_bot_tool.py. Run directly from a real terminal (not through the app
or an automated script) - Telegram sends a login code to that account's app/
SMS, and this will prompt you to type it in.

Setup:
  1. Log into https://my.telegram.org/apps using the DEDICATED account's phone
     number (NOT your main Telegram account).
  2. Create an app there, copy its "api_id" and "api_hash".
  3. Save them: open config/api_keys.json and set "telegram_api_id" and
     "telegram_api_hash" (or add a Settings UI field for them later).
  4. Run: python core/telegram_setup.py
  5. Enter the dedicated account's phone number, then the code Telegram sends.

This creates config/telegram_osint.session, which telegram_bot_tool.py reuses
for every future query - you only do this once.
"""
import asyncio
import os
import sys

sys.path.append(os.path.dirname(__file__))

from telethon import TelegramClient
from config import get_key

SESSION_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "telegram_osint")


async def main():
    api_id = get_key("telegram_api_id")
    api_hash = get_key("telegram_api_hash")
    if not api_id or not api_hash:
        print("Missing telegram_api_id / telegram_api_hash in config/api_keys.json.")
        print("Get them from https://my.telegram.org/apps, logged in as the DEDICATED OSINT account.")
        return

    client = TelegramClient(SESSION_PATH, int(api_id), api_hash)
    await client.start()  # prompts for phone number + login code right here in the terminal
    me = await client.get_me()
    print(f"Logged in as: {me.first_name} (@{me.username or 'no username'})")
    print(f"Session saved to: {SESSION_PATH}.session - telegram_bot_tool.py will reuse it from now on.")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
