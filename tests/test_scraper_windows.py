import sys
import os
import asyncio
import time

# 1. Simulate the Fix in main.py
if sys.platform == 'win32':
    print("[TEST] Setting WindowsProactorEventLoopPolicy...")
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Setup path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../core")))

# Import AFTER setting policy (critical simulation)
from scraper import fetch_dynamic_page

async def main():
    target = "https://yandex.ru/maps"
    print(f"[TEST] Fetching {target}...")
    try:
        start = time.time()
        text = await fetch_dynamic_page(target)
        duration = time.time() - start
        
        print(f"[TEST] Done in {duration:.2f}s")
        print(f"[TEST] Content Length: {len(text)}")
        print(f"[TEST] Snapshot: {text[:200]}...")
        
        if len(text) > 500:
            print("[TEST] SUCCESS: Content fetched!")
        else:
            print("[TEST] FAIL: Content too short.")
            
    except Exception as e:
        print(f"[TEST] CRASH: {e}")

if __name__ == "__main__":
    asyncio.run(main())
