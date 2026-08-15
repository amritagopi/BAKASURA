from ddgs import DDGS
import time
import random
from typing import List, Dict

import json
import os
import requests

from config import load_keys as _get_api_keys
from api_services import search_brave, search_exa, search_searxng

def perform_search(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    """
    Orchestrator: Prioritizes official APIs with their own dedicated quota
    (Brave/Exa - configured via config/api_keys.json), THEN the local SearXNG
    instance (shared with other tools, e.g. OpenClaw - has its own upstream
    rate limits, so it's not free capacity), and finally DDG's multi-engine
    scrape as a last resort.
    """
    results = []

    # 1. BRAVE (Priority 1 - dedicated API quota, doesn't compete with SearXNG)
    try:
        results = search_brave(query, max_results)
        if results:
            print(f"[API SUCCESS] Brave found {len(results)} results for: {query}")
            return results
        else:
            print(f"[API INFO] Brave returned 0 results for: {query} (or key missing)")
    except Exception as e:
        print(f"[API WARN] Brave search failed: {e}")

    # 2. EXA (Priority 2 - dedicated API quota)
    try:
        results = search_exa(query, max_results)
        if results:
            print(f"[API SUCCESS] Exa found {len(results)} results for: {query}")
            return results
        else:
            print(f"[API INFO] Exa returned 0 results for: {query} (or key missing)")
    except Exception as e:
        print(f"[API WARN] Exa search failed: {e}")

    # 3. SEARXNG (Priority 3 - shared local instance. Its own upstream engines
    # get rate-limited/CAPTCHA'd by Google/Brave/DuckDuckGo under burst traffic,
    # so a courtesy delay here protects OTHER clients of this same instance too,
    # not just us.)
    time.sleep(random.uniform(2.0, 4.0))
    try:
        results = search_searxng(query, max_results)
        if results:
            print(f"[API SUCCESS] SearXNG found {len(results)} results for: {query}")
            return results
        else:
            print(f"[API INFO] SearXNG returned 0 results for: {query} (or instance/engines unavailable)")
    except Exception as e:
        print(f"[API WARN] SearXNG search failed: {e}")

    # 4. DUCKDUCKGO (Fallback)
    results = []
    print(f"[FALLBACK] Hunting via DuckDuckGo: {query}")
    
    # Small delay to be polite
    time.sleep(random.uniform(1.0, 2.0))
    
    try:
        with DDGS(timeout=20) as ddgs:
            # Use default backend (auto), which is most reliable across versions
            ddg_gen = ddgs.text(query, max_results=max_results)
            
            for r in ddg_gen:
                results.append({
                    "title": r.get('title', ''),
                    "href": r.get('href', ''),
                    "body": r.get('body', '')
                })
        
        if results:
            print(f"[DDG SUCCESS] Found {len(results)} results")
        else:
            print(f"[DDG INFO] No results found for: {query}")
                
    except Exception as e:
        print(f"[WARN] DDG Search failed: {e}")
        # Retry once with html backend if api fails
        try:
             print("[DDG] Retrying with 'html' backend...")
             time.sleep(2)
             with DDGS(timeout=20) as ddgs:
                ddg_gen = ddgs.text(query, max_results=max_results, backend='html')
                for r in ddg_gen:
                    results.append({
                        "title": r.get('title', ''),
                        "href": r.get('href', ''),
                        "body": r.get('body', '')
                    })
             if results:
                 print(f"[DDG RETRY SUCCESS] Found {len(results)} results")
        except Exception as e2:
            print(f"[WARN] DDG Retry failed: {e2}")

    return results

if __name__ == "__main__":
    res = perform_search("Python programming", 3)
    for r in res:
        print(f"Found: {r['title']} -> {r['href']}")
