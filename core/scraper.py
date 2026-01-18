import asyncio
from playwright.async_api import async_playwright
import random
import time

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]

async def _fetch_with_playwright(url: str) -> str:
    """
    Async implementation of heavy scraping with stealth techniques.
    """
    async with async_playwright() as p:
        # Launch options to avoid detection
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--window-position=0,0",
                "--ignore-certifcate-errors",
                "--ignore-certifcate-errors-spki-list",
                "--disable-accelerated-2d-canvas",
                "--disable-gpu",
            ]
        )
        
        # Context with stealth settings
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1920, "height": 1080},
            locale="ru-RU", # Match target region
            timezone_id="Europe/Moscow",
            java_script_enabled=True,
        )
        
        # Inject stealth scripts to hide webdriver property
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        page = await context.new_page()
        
        print(f"[SCRAPER] Navigating to {url}...")
        try:
            # 1. Navigation
            # Wait for networkidle (safer for SPAs)
            response = await page.goto(url, timeout=45000, wait_until="domcontentloaded")
            
            # 2. Heuristic Wait (Wait for body to actually have content)
            # Sometimes 'domcontentloaded' fires on the skeleton.
            await page.wait_for_timeout(5000) # Give it a solid 5s for React/Vue hydration
            
            # 3. Scroll to trigger lazy loading
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)
            
            # 4. Get content (VISIBLE TEXT ONLY)
            # This is cleaner than getting HTML and parsing it, as browser rendering handles visibility.
            text_content = await page.evaluate("document.body.innerText")
            
            # Fallback if body is empty (e.g. frameset)
            if not text_content or len(text_content) < 50:
                 # Try to get frame text if main body is empty
                 frames = page.frames
                 for frame in frames:
                     try:
                         t = await frame.evaluate("document.body.innerText")
                         if t and len(t) > len(text_content):
                             text_content += "\n" + t
                     except: pass

            await browser.close()
            return text_content
            
        except Exception as e:
            await browser.close()
            print(f"[SCRAPER ERROR] Failed to fetch {url}: {e}")
            return ""

# Expose the async function directly for agent.py
async def fetch_dynamic_page(url: str) -> str:
    """
    Async wrapper for Playwright scraping.
    """
    try:
        return await _fetch_with_playwright(url)
    except Exception as e:
        print(f"[SCRAPER CRITICAL] Asyncio loop error: {e}")
        return ""

if __name__ == "__main__":
    # Test
    test_url = "https://yandex.ru/maps" 
    print(f"Testing scraper on {test_url}...")
    # asyncio.run() is ONLY for the main entry point logic
    html = asyncio.run(_fetch_with_playwright(test_url))
    print(f"Got {len(html)} bytes")
