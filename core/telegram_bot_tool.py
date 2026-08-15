"""
Telethon-driven queries against public Telegram OSINT bots (VkHistoryRobot,
AllOSINTrobot - from github.com/paulpogoda/OSINT-Tools-Russia).

Uses a DEDICATED Telegram account, never the user's main one - see
core/telegram_setup.py for the one-time interactive login that creates the
session file. Degrades to an empty result (never raises) if credentials or
the session aren't set up yet, same convention as api_services.py.

Neither bot has a documented command protocol - the send/parse logic here is
a best-effort guess from their public descriptions and MUST be checked against
real replies after the first live login, then adjusted.

!!! PACING WARNING - READ BEFORE TESTING !!!
This is an ACCOUNT-BOUND integration, unlike the rest of core/ (Pogoda CSE,
Getcontact, 220vk/regvk, lyzem, nalog.ru are all anonymous no-login lookups
with no reputation at stake). Telegram froze the first dedicated OSINT account
used for this module on 2026-08-15 after a diagnostic script resolved several
usernames back-to-back right after first login - a classic bot-abuse pattern.
A module-level minimum delay is enforced below as a hard guard, but that alone
is NOT enough: also let a brand-new account "warm up" with real human usage
(join a channel or two, add a contact, wait a day+) before ever scripting
against it, and never loop over multiple bot/entity lookups in one run.
"""
import asyncio
import os
import time
from typing import Dict, List, Optional

from telethon import TelegramClient, events
from telethon.tl.custom.message import Message

from config import get_key

SESSION_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "telegram_osint")

VK_HISTORY_BOT = "VKHistoryRobot"
ALL_OSINT_BOT = "AllOSINTrobot"

MIN_SECONDS_BETWEEN_CALLS = 20.0
_last_call_ts: Optional[float] = None


def _throttle():
    """Hard floor on call spacing - see the pacing warning above. Sleeps if called too soon."""
    global _last_call_ts
    now = time.time()
    if _last_call_ts is not None:
        wait = MIN_SECONDS_BETWEEN_CALLS - (now - _last_call_ts)
        if wait > 0:
            print(f"[TELEGRAM] Throttling {wait:.1f}s before next request - do not bypass this.")
            time.sleep(wait)
    _last_call_ts = time.time()


def _get_client() -> Optional[TelegramClient]:
    api_id = get_key("telegram_api_id")
    api_hash = get_key("telegram_api_hash")
    if not api_id or not api_hash:
        return None
    return TelegramClient(SESSION_PATH, int(api_id), api_hash)


def _extract_buttons(message: Message) -> str:
    if not message or not message.buttons:
        return ""
    labels = []
    for row in message.buttons:
        for b in row:
            labels.append(getattr(b, "text", "") or getattr(b, "url", "") or "")
    return " | ".join(l for l in labels if l)


async def _query_bot(bot_username: str, message: str, wait_seconds: float = 12.0, max_replies: int = 5) -> List[Dict[str, str]]:
    client = _get_client()
    if not client:
        print("[TELEGRAM] telegram_api_id/telegram_api_hash not configured - skipping.")
        return []

    async with client:
        if not await client.is_user_authorized():
            print("[TELEGRAM] Session not authorized - run `python core/telegram_setup.py` once, interactively.")
            return []

        entity = await client.get_entity(bot_username)
        replies: List[Dict[str, str]] = []

        async def _collect(event):
            replies.append({
                "text": event.raw_text or "",
                "buttons": _extract_buttons(event.message),
            })

        client.add_event_handler(_collect, events.NewMessage(chats=entity, incoming=True))

        print(f"[TELEGRAM] -> @{bot_username}: {message}")
        await client.send_message(entity, message)

        elapsed = 0.0
        step = 1.0
        while elapsed < wait_seconds and len(replies) < max_replies:
            await asyncio.sleep(step)
            elapsed += step

        client.remove_event_handler(_collect)
        print(f"[TELEGRAM] <- @{bot_username}: {len(replies)} repl(y/ies)")
        return replies


def query_vk_history_bot_sync(vk_query: str) -> List[Dict[str, str]]:
    """
    vk_query: a vk.com profile URL, numeric VK id, or username. Exact accepted
    format is unverified until tested against the real bot - adjust as needed.
    """
    _throttle()
    try:
        return asyncio.run(_query_bot(VK_HISTORY_BOT, vk_query))
    except Exception as e:
        print(f"[TELEGRAM] VkHistoryRobot query failed: {e}")
        return []


def query_all_osint_bot_sync(keyword: str) -> List[Dict[str, str]]:
    """
    AllOSINTrobot is a CATALOGUE/directory bot - per its description it returns
    a list of other bots matching a keyword/data-type, not personal data
    directly. Useful for discovering which specialized bot to query next, not
    as a per-target automated lookup - kept separate from the snowball loop
    for that reason (see agent.py).
    """
    _throttle()
    try:
        return asyncio.run(_query_bot(ALL_OSINT_BOT, keyword))
    except Exception as e:
        print(f"[TELEGRAM] AllOSINTrobot query failed: {e}")
        return []


if __name__ == "__main__":
    # DISABLED 2026-08-15: dedicated account got frozen after test queries - do not
    # re-enable until the account is fixed/replaced (see feedback_account_bound_automation
    # memory). Uncomment only once ready to test again, and one call at a time.
    # for r in query_vk_history_bot_sync("durov"):
    #     print(r)
    print("[TELEGRAM] __main__ block disabled - account is frozen, see comment above.")
