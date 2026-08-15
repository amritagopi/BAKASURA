"""
Getcontact free web lookup - lookup.getcontact.com/en/p/<countrycode><number>.
No login, no API key, no CAPTCHA hit in testing - just a direct URL fetched the
same stealth-Playwright way as scraper.py.

CAVEAT: only tested against throwaway numbers with zero community reports, which
render Getcontact's "no result" placeholder (detected here via the img[src*=no-result]
that page always shows). What a genuine MATCH renders like is unconfirmed - this
returns the full visible text of the results section for a real number so the LLM
analysis step can read whatever shape it turns out to be, rather than guessing at
field-level parsing that's never been seen populated.
"""
import asyncio
from typing import Dict, Optional

import phonenumbers
from playwright.async_api import async_playwright

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"


async def _lookup(phone: str) -> Optional[Dict]:
    parsed = phonenumbers.parse(phone, None)
    if not phonenumbers.is_valid_number(parsed):
        return None

    url = f"https://lookup.getcontact.com/en/p/{parsed.country_code}{parsed.national_number}"

    browser = await async_playwright().start()
    chrome = await browser.chromium.launch(headless=True, args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
    try:
        context = await chrome.new_context(user_agent=USER_AGENT)
        page = await context.new_page()
        await page.goto(url, timeout=45000, wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)

        no_result = await page.evaluate("() => !!document.querySelector('img[src*=\"no-result\"]')")
        text = await page.evaluate("document.body.innerText")
    finally:
        await chrome.close()
        await browser.stop()

    if no_result:
        print(f"[GETCONTACT] No community data for {url}")
        return {"url": url, "found": False}

    print(f"[GETCONTACT] Possible match at {url} - check raw_text")
    return {"url": url, "found": True, "raw_text": text[:2000]}


def lookup_getcontact_sync(phone: str) -> Optional[Dict]:
    try:
        return asyncio.run(_lookup(phone))
    except Exception as e:
        print(f"[GETCONTACT] Lookup failed for {phone}: {e}")
        return None


if __name__ == "__main__":
    print(lookup_getcontact_sync("+79261234567"))
