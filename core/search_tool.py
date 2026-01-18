from ddgs import DDGS
import time
import random
from typing import List, Dict

def perform_search(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    """
    Searches using DuckDuckGo (DDGS library).
    Robust, no 429s, no HTML parsing needed.
    """
    results = []
    print(f"Hunting via DuckDuckGo: {query}")
    
    # Small delay to be polite
    time.sleep(random.uniform(1.0, 2.0))
    
    try:
        with DDGS() as ddgs:
            # backend='api' is usually fastest and most stable
            ddg_gen = ddgs.text(query, max_results=max_results, backend='api')
            
            for r in ddg_gen:
                results.append({
                    "title": r.get('title', ''),
                    "href": r.get('href', ''),
                    "body": r.get('body', '')
                })
                
    except Exception as e:
        print(f"[WARN] DDG Search failed: {e}")
        # Retry once with html backend if api fails
        try:
             time.sleep(2)
             with DDGS() as ddgs:
                ddg_gen = ddgs.text(query, max_results=max_results, backend='html')
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
