"""
Full-text Telegram channel/group/bot search via lyzem.com - matches names/bios,
no login, no API key, no CAPTCHA hit in testing.

Also evaluated: tgstat.ru sits behind the same Cloudflare challenge our stealth
Playwright doesn't clear (same wall as start.me/vk.watch). telegramchannels.me
turned out to be a browse/ranking directory (categories, trending charts), not
a per-name search tool - it stays a manual link only in osint_resources.json.
"""
import asyncio
import urllib.parse
from typing import Dict, List

from playwright.async_api import async_playwright

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"


async def _search_lyzem(query: str, max_results: int) -> List[Dict[str, str]]:
    url = f"https://lyzem.com/search?q={urllib.parse.quote(query)}"

    browser = await async_playwright().start()
    chrome = await browser.chromium.launch(headless=True, args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
    try:
        context = await chrome.new_context(user_agent=USER_AGENT)
        page = await context.new_page()
        await page.goto(url, timeout=45000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        raw = await page.evaluate("""
            () => Array.from(document.querySelectorAll('.search-result')).map(el => {
                const titleA = el.querySelector('.search-result-title a');
                const descrA = el.querySelector('.search-result-descr a');
                return {
                    title: titleA ? titleA.innerText.trim() : '',
                    href: titleA ? titleA.href : '',
                    body: descrA ? descrA.innerText.trim() : '',
                };
            })
        """)
    finally:
        await chrome.close()
        await browser.stop()

    seen = set()
    results = []
    for r in raw:
        href = r.get("href")
        if not href or href in seen:
            continue
        seen.add(href)
        results.append(r)
        if len(results) >= max_results:
            break
    return results


def search_lyzem_sync(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    try:
        print(f"[LYZEM] Searching Telegram channels/groups/bots: {query}")
        results = asyncio.run(_search_lyzem(query, max_results))
        print(f"[LYZEM] Found {len(results)} result(s)")
        return results
    except Exception as e:
        print(f"[LYZEM] Error: {e}")
        return []


if __name__ == "__main__":
    for r in search_lyzem_sync("test", 5):
        print(r)
