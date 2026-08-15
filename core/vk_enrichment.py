"""
VK-specific profile enrichment. Once a vk.com/<id> URL turns up in gathered_data,
these two free tools surface things VK hides from logged-out visitors:
  - 220vk.com  - friend/subscription change history, birthdate, online status
  - regvk.com  - account registration date (useful age-of-account signal)
Both work with zero login, no API key, no CAPTCHA hit in testing - see agent.py's
enrich_node for how they're triggered per newly-discovered profile.

Also evaluated and rejected for this module:
  - vk.watch       - sits behind a Cloudflare challenge our stealth Playwright
                     setup doesn't clear (same wall start.me sits behind).
  - vk.barkov.net  - requires the OPERATOR to log in with their own VK account
                     (OAuth) before returning anything - not a no-login lookup.
  - photo-map.ru   - same OAuth-login requirement, since VK's 2018 API policy
                     change (photo/geo search needs an authenticated session).
"""
import asyncio
import re
from typing import Dict, Optional

from playwright.async_api import async_playwright

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"

VK_URL_RE = re.compile(r"vk\.com/([a-zA-Z0-9_.]+)")
_NON_PROFILE_PATHS = {"id", "wall", "video", "photo", "away", "away.php", "club", "public", "feed", "im"}


def extract_vk_id(url: str) -> Optional[str]:
    """Pulls the profile slug/id out of a vk.com URL, or None if it's not a profile link."""
    m = VK_URL_RE.search(url or "")
    if not m:
        return None
    vk_id = m.group(1)
    if vk_id.lower() in _NON_PROFILE_PATHS:
        return None
    return vk_id


async def _fetch_220vk(vk_id: str) -> str:
    browser = await async_playwright().start()
    chrome = await browser.chromium.launch(headless=True, args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
    try:
        context = await chrome.new_context(user_agent=USER_AGENT)
        page = await context.new_page()
        await page.goto(f"https://220vk.com/{vk_id}?i", timeout=45000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        return await page.evaluate("document.body.innerText")
    finally:
        await chrome.close()
        await browser.stop()


async def _fetch_regvk(vk_id: str) -> str:
    browser = await async_playwright().start()
    chrome = await browser.chromium.launch(headless=True, args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
    try:
        context = await chrome.new_context(user_agent=USER_AGENT)
        page = await context.new_page()
        await page.goto("https://regvk.com", timeout=45000, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)
        await page.fill("#enter", vk_id)
        await page.click("button[type=submit]")
        await page.wait_for_timeout(4000)
        return await page.evaluate("document.body.innerText")
    finally:
        await chrome.close()
        await browser.stop()


def enrich_vk_profile_sync(vk_id: str) -> Dict[str, str]:
    """Runs both 220vk (activity/friend history) and regvk (registration date) for one VK id."""
    result: Dict[str, str] = {}
    try:
        result["220vk"] = asyncio.run(_fetch_220vk(vk_id))
    except Exception as e:
        print(f"[VK ENRICH] 220vk failed for {vk_id}: {e}")
    try:
        result["regvk"] = asyncio.run(_fetch_regvk(vk_id))
    except Exception as e:
        print(f"[VK ENRICH] regvk failed for {vk_id}: {e}")
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(enrich_vk_profile_sync("id1"), ensure_ascii=False, indent=2)[:1500])
