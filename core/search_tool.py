"""
Smart Search Tool for Bakasura
Priority: Brave API > Exa API > DuckDuckGo (free fallback)
"""
from ddgs import DDGS
import time
import random
from typing import List, Dict

# Import API services (they handle missing keys gracefully)
try:
    from api_services import search_brave, search_exa
except ImportError:
    # Fallback if api_services not available
    def search_brave(q, m): return []
    def search_exa(q, m): return []


def perform_search(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    """
    Smart search with API fallback chain:
    1. Try Brave Search API (if key exists)
    2. Try Exa.ai API (if key exists)  
    3. Fall back to DuckDuckGo (always free)
    """
    
    # === TIER 1: Brave Search API ===
    results = search_brave(query, max_results)
    if results:
        return results
    
    # === TIER 2: Exa.ai API ===
    results = search_exa(query, max_results)
    if results:
        return results
    
    # === TIER 3: DuckDuckGo (Free Fallback) ===
    print(f"Hunting via DuckDuckGo: {query}")
    results = []
    
    # Small delay to be polite
    time.sleep(random.uniform(0.5, 1.5))
    
    try:
        with DDGS() as ddgs:
            ddg_gen = ddgs.text(query, max_results=max_results)
            
            for r in ddg_gen:
                results.append({
                    "title": r.get('title', ''),
                    "href": r.get('href', ''),
                    "body": r.get('body', '')
                })
                
    except Exception as e:
        print(f"[WARN] DDG Search failed: {e}")
        # Retry once
        try:
            time.sleep(2)
            with DDGS() as ddgs:
                ddg_gen = ddgs.text(query, max_results=max_results)
                for r in ddg_gen:
                    results.append({
                        "title": r.get('title', ''),
                        "href": r.get('href', ''),
                        "body": r.get('body', '')
                    })
        except Exception as e2:
            print(f"[WARN] DDG Retry failed: {e2}")

    print(f"Found {len(results)} results")
    return results


if __name__ == "__main__":
    res = perform_search("Python programming", 3)
    for r in res:
        print(f"Found: {r['title']} -> {r['href']}")
