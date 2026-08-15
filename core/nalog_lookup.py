"""
Free official RU government lookup via service.nalog.ru (FNS/tax service).

Only the "invalid INN" checker (invalid-inn-fl.html) is wired in - it just takes
a 12-digit personal INN, no login, no CAPTCHA in testing (the submit button just
needs real keystrokes, not .fill(), to enable itself via the page's own JS).

Two other RU-govt tools from the source list were evaluated and left out:
  - service.nalog.ru's "determine INN from personal data" (inn.do) needs full
    name + birthdate + passport series/number/issue date - fields TargetProfile
    doesn't collect - and has a hidden captchaToken field implying a CAPTCHA
    gate on submit.
  - The old FMS/MVD invalid-passport checker (services.fms.gov.ru) is dead -
    FMS was merged into MVD years ago - and a working replacement URL for the
    modern passport-validity service wasn't found.
"""
import asyncio
from typing import Dict, Optional

from playwright.async_api import async_playwright

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"

# Standard FNS checksum weights for a 12-digit personal INN.
_W11 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
_W12 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]


def is_valid_inn_checksum(inn: str) -> bool:
    """Filters regex noise (order numbers, tracking codes, etc.) before we bother querying nalog.ru."""
    if not inn or not inn.isdigit() or len(inn) != 12:
        return False
    digits = [int(c) for c in inn]
    n11 = sum(d * w for d, w in zip(digits[:10], _W11)) % 11 % 10
    n12 = sum(d * w for d, w in zip(digits[:11], _W12)) % 11 % 10
    return n11 == digits[10] and n12 == digits[11]


async def _check_invalid_inn(inn: str) -> Dict:
    browser = await async_playwright().start()
    chrome = await browser.chromium.launch(headless=True, args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
    try:
        context = await chrome.new_context(user_agent=USER_AGENT, locale="ru-RU")
        page = await context.new_page()
        await page.goto("https://service.nalog.ru/invalid-inn-fl.html", timeout=45000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        await page.click("#inn")
        await page.type("#inn", inn, delay=40)  # real keystrokes - .fill() doesn't trigger the JS that enables submit
        await page.wait_for_timeout(500)

        if await page.evaluate("document.querySelector('button[type=submit]').disabled"):
            return {"checked": False}

        await page.evaluate("document.querySelector('button[type=submit]').click()")
        await page.wait_for_timeout(4000)
        text = await page.evaluate("document.body.innerText")
    finally:
        await chrome.close()
        await browser.stop()

    invalid = "Информация не найдена" not in text
    return {"checked": True, "invalid": invalid, "raw_text": text}


def check_inn_invalid_sync(inn: str) -> Optional[Dict]:
    """Returns None for anything that fails the checksum (not a real INN) or on any failure."""
    if not is_valid_inn_checksum(inn):
        return None
    try:
        return asyncio.run(_check_invalid_inn(inn))
    except Exception as e:
        print(f"[NALOG] Invalid-INN check failed for {inn}: {e}")
        return None


if __name__ == "__main__":
    print(check_inn_invalid_sync("500100732259"))
