"""
Pogoda RU/CIS Custom Search Engine (github.com/paulpogoda/OSINT-Tools-Russia).
A Google Programmable Search Engine scoped to VK/OK/Facebook/LinkedIn/Telegram/
Dzen/TikTok/Instagram/LiveJournal/Dvach/Wayback/KinoPoisk/Threads/BlueSky/Reddit -
useful for RU/CIS-speaking targets. No API key needed: the standalone results page
renders client-side off the #gsc.q= hash, so we drive it with the same Playwright
approach as scraper.py rather than the (key-gated) Google Custom Search JSON API.
"""
import asyncio
import urllib.parse
from typing import List, Dict

from playwright.async_api import async_playwright

CX = "029ffbc44aa3946cb"


async def _search_pogoda_cse(query: str, max_results: int) -> List[Dict[str, str]]:
    q_enc = urllib.parse.quote(query)
    url = f"https://cse.google.com/cse?cx={CX}#gsc.tab=0&gsc.q={q_enc}"

    browser = await async_playwright().start()
    chrome = await browser.chromium.launch(headless=True, args=["--no-sandbox"])
    try:
        page = await chrome.new_page()
        await page.goto(url, timeout=45000, wait_until="domcontentloaded")
        await page.wait_for_timeout(6000)  # widget needs time to hydrate + fetch results

        raw = await page.evaluate("""
            () => {
                const out = [];
                document.querySelectorAll('.gsc-webResult').forEach(el => {
                    const titleEl = el.querySelector('a.gs-title');
                    const snippetEl = el.querySelector('.gs-snippet');
                    if (titleEl && titleEl.href) {
                        out.push({
                            title: titleEl.innerText || titleEl.textContent || '',
                            href: titleEl.href,
                            body: snippetEl ? (snippetEl.innerText || snippetEl.textContent || '') : ''
                        });
                    }
                });
                return out;
            }
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
        results.append({"title": r.get("title", ""), "href": href, "body": r.get("body", "")})
        if len(results) >= max_results:
            break
    return results


def search_pogoda_cse_sync(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    """Synchronous wrapper - safe to call via asyncio.to_thread() from agent.py."""
    try:
        print(f"[POGODA CSE] Searching RU/CIS social CSE: {query}")
        results = asyncio.run(_search_pogoda_cse(query, max_results))
        print(f"[POGODA CSE] Found {len(results)} result(s)")
        return results
    except Exception as e:
        print(f"[POGODA CSE] Error: {e}")
        return []


if __name__ == "__main__":
    for r in search_pogoda_cse_sync("test query", 5):
        print(r)
