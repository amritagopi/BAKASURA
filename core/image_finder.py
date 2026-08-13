"""
Free reverse-image / face-pivot search for Bakasura.
No paid API (PimEyes/FaceCheck.ID) involved - this is a best-effort scrape of
Yandex Images' "search by this image URL" feature, which OSINT practitioners rate
as the strongest free face-matching engine available. It is explicitly best-effort:
Yandex's DOM/anti-bot behavior can change or block headless traffic at any time, so
every failure mode here degrades to "found nothing" rather than raising.
"""
import asyncio
import re
from typing import Dict, List, Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
}

# Own-domain / boilerplate hosts to drop from reverse-image results - they're
# Yandex UI chrome, not intel about the target.
NOISE_DOMAINS = [
    "yandex.", "ya.ru", "captcha", "showcaptcha",
]


def extract_profile_image(url: str) -> Optional[str]:
    """
    Fetches a page's raw HTML directly (no browser needed - og:image/twitter:image
    meta tags are meant for crawlers/link previews, so they're present even on
    JS-heavy pages) and pulls the most likely profile photo URL.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        for selector in (
            {"property": "og:image"},
            {"name": "twitter:image"},
            {"property": "og:image:secure_url"},
        ):
            tag = soup.find("meta", attrs=selector)
            if tag and tag.get("content"):
                return tag["content"]
        return None
    except Exception as e:
        print(f"[IMAGE FINDER] Could not extract profile image from {url}: {e}")
        return None


async def _reverse_search_yandex_async(image_url: str) -> List[Dict[str, str]]:
    from playwright.async_api import async_playwright

    search_url = f"https://yandex.com/images/search?rpt=imageview&url={quote(image_url, safe='')}"
    results: List[Dict[str, str]] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            context = await browser.new_context(
                user_agent=HEADERS["User-Agent"],
                viewport={"width": 1600, "height": 1000},
            )
            page = await context.new_page()
            await page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)

            if "showcaptcha" in page.url or "captcha" in page.url:
                print("[REVERSE IMAGE] Yandex served a CAPTCHA - skipping, no results.")
                return []

            anchors = await page.eval_on_selector_all(
                "a[href^='http']",
                "els => els.map(e => ({href: e.href, text: e.innerText || ''}))",
            )
            seen = set()
            for a in anchors:
                href = a.get("href", "")
                text = (a.get("text") or "").strip()
                if not href or href in seen:
                    continue
                if any(n in href.lower() for n in NOISE_DOMAINS):
                    continue
                seen.add(href)
                results.append({"href": href, "title": text[:150] or "Visually similar page"})
                if len(results) >= 8:
                    break
        finally:
            await browser.close()

    return results


def reverse_search_yandex(image_url: str) -> List[Dict[str, str]]:
    """Sync wrapper - safe to call via asyncio.to_thread() from agent.py."""
    try:
        return asyncio.run(_reverse_search_yandex_async(image_url))
    except Exception as e:
        print(f"[REVERSE IMAGE] Yandex search failed: {e}")
        return []
