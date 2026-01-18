"""
Smart Search Tool for Bakasura (Stable Edition)
Priority: Brave API > Google (Fallback)
"""
import time
import random
from typing import List, Dict

# Import API services
try:
    from api_services import search_brave, search_exa
except ImportError:
    def search_brave(q, m): return []
    def search_exa(q, m): return []

# Fallback using 'googlesearch-python' library
try:
    from googlesearch import search as google_search
except ImportError:
    google_search = None

def perform_search(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    """
    Search execution with strict error handling.
    """
    all_results = []
    
    # 1. BRAVE API (Premium) - Спим, чтобы не ловить 429 (Rate Limit)
    time.sleep(1.1) 
    try:
        brave_res = search_brave(query, max_results)
        if brave_res:
            print(f"[SEARCH] Brave found {len(brave_res)} results.")
            return brave_res
    except Exception as e:
        print(f"[WARN] Brave API failed: {e}")

    # 2. EXA API (Semantic)
    try:
        exa_res = search_exa(query, max_results)
        if exa_res:
            print(f"[SEARCH] Exa found {len(exa_res)} results.")
            return exa_res
    except Exception as e:
        print(f"[WARN] Exa API failed: {e}")

    # 3. GOOGLE FALLBACK (Free, Selenium-less)
    print(f"[SEARCH] Falling back to Google for: {query}")
    if google_search:
        try:
            # Google возвращает только URL, но это лучше, чем ничего
            # advanced=True дает объекты с title/description
            g_results = google_search(query, num_results=max_results, advanced=True)
            for res in g_results:
                all_results.append({
                    "title": res.title,
                    "href": res.url,
                    "body": res.description
                })
            print(f"[SEARCH] Google found {len(all_results)} results.")
            return all_results
        except Exception as e:
            print(f"[WARN] Google Search failed: {e}")
    else:
        print("[ERR] 'googlesearch-python' not installed. Fallback failed.")

    return []

if __name__ == "__main__":
    # Test run
    print(perform_search("test query", 3))
