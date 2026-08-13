"""
API Service Integrations for Bakasura
Each function returns results or empty list on failure. Never crashes.
"""
import requests
from typing import List, Dict, Optional
from config import get_key

# ============================================================
# PRIMARY SEARCH APIS (Use instead of DuckDuckGo if available)
# ============================================================

def search_searxng(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    """
    Self-hosted SearXNG metasearch instance (Docker).
    Requires `search.formats: [html, json]` enabled in the instance's settings.yml.
    URL is configurable via config/api_keys.json ("searxng_url"), defaults to localhost:8080.
    """
    base_url = get_key("searxng_url") or "http://localhost:8080"

    print(f"[SEARXNG] Searching: {query}")

    try:
        resp = requests.get(
            f"{base_url.rstrip('/')}/search",
            params={"q": query, "format": "json"},
            timeout=15
        )

        if resp.status_code != 200:
            print(f"[SEARXNG] Error {resp.status_code}, continuing...")
            return []

        data = resp.json()
        results = []
        for item in data.get("results", [])[:max_results]:
            results.append({
                "title": item.get("title", ""),
                "href": item.get("url", ""),
                "body": item.get("content", "")
            })

        print(f"[SEARXNG] Found {len(results)} results")
        return results

    except Exception as e:
        print(f"[SEARXNG] Error: {e}, continuing...")
        return []


def search_brave(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    """
    Brave Search API - 2000 free requests/month
    https://brave.com/search/api/
    """
    api_key = get_key("brave_search")
    if not api_key:
        return []
    
    print(f"[BRAVE API] Searching: {query}")
    
    try:
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": api_key
        }
        params = {
            "q": query,
            "count": max_results,
            "safesearch": "off",
            "text_decorations": 0
        }
        resp = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers=headers,
            params=params,
            timeout=15
        )
        
        if resp.status_code != 200:
            print(f"[BRAVE API] Error {resp.status_code}: {resp.text}")
            return []
        
        data = resp.json()
        results = []
        for item in data.get("web", {}).get("results", [])[:max_results]:
            results.append({
                "title": item.get("title", ""),
                "href": item.get("url", ""),
                "body": item.get("description", "")
            })
        
        # RETRY LOGIC: If 0 results and query has quotes, try without quotes
        if not results and '"' in query:
            print("[BRAVE API] 0 results with quotes, retrying without quotes...")
            simplified_query = query.replace('"', '')
            return search_brave(simplified_query, max_results)

        print(f"[BRAVE API] Found {len(results)} results")
        return results
        
    except Exception as e:
        print(f"[BRAVE API] Error: {e}")
        return []


def search_exa(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    """
    Exa.ai Semantic Search - 1000 free requests/month
    https://exa.ai/
    """
    api_key = get_key("exa_ai")
    if not api_key:
        return []
    
    print(f"[EXA API] Searching: {query}")
    
    try:
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key
        }
        payload = {
            "query": query,
            "numResults": max_results,
            "type": "auto",
            "useAutoprompt": True,
            "contents": {
                "text": {"maxCharacters": 1000}
            }
        }
        resp = requests.post(
            "https://api.exa.ai/search",
            headers=headers,
            json=payload,
            timeout=20
        )
        
        if resp.status_code == 429:
            print("[EXA API] Rate limit exceeded, continuing...")
            return []
        if resp.status_code == 401:
            print("[EXA API] Invalid API key, continuing...")
            return []
        if resp.status_code != 200:
            print(f"[EXA API] Error {resp.status_code}, continuing...")
            return []
        
        data = resp.json()
        results = []
        for item in data.get("results", [])[:max_results]:
            results.append({
                "title": item.get("title", ""),
                "href": item.get("url", ""),
                "body": item.get("text", "")[:500]
            })
        
        print(f"[EXA API] Found {len(results)} results")
        return results
        
    except Exception as e:
        print(f"[EXA API] Error: {e}, continuing...")
        return []


# ============================================================
# ENRICHMENT APIS (Use at the end for extra intel)
# ============================================================

def enrich_hunter_email(domain: str) -> List[Dict[str, str]]:
    """
    Hunter.io - Find emails by domain - 25 free/month
    """
    api_key = get_key("hunter_io")
    if not api_key:
        return []
    
    print(f"[HUNTER.IO] Looking up domain: {domain}")
    
    try:
        resp = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": api_key},
            timeout=15
        )
        
        if resp.status_code != 200:
            print(f"[HUNTER.IO] Error {resp.status_code}, continuing...")
            return []
        
        data = resp.json()
        emails = []
        for email_data in data.get("data", {}).get("emails", []):
            emails.append({
                "email": email_data.get("value", ""),
                "confidence": email_data.get("confidence", 0),
                "type": email_data.get("type", "")
            })
        
        print(f"[HUNTER.IO] Found {len(emails)} emails")
        return emails
        
    except Exception as e:
        print(f"[HUNTER.IO] Error: {e}, continuing...")
        return []


def enrich_hibp(email: str) -> List[Dict[str, str]]:
    """
    Have I Been Pwned - Check email breaches - Free (with attribution)
    Note: Requires API key for v3 API
    """
    api_key = get_key("hibp")
    if not api_key:
        return []
    
    print(f"[HIBP] Checking breaches for: {email}")
    
    try:
        headers = {
            "hibp-api-key": api_key,
            "User-Agent": "Bakasura-OSINT"
        }
        resp = requests.get(
            f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}",
            headers=headers,
            timeout=15
        )
        
        if resp.status_code == 404:
            print("[HIBP] No breaches found (good!)")
            return []
        if resp.status_code != 200:
            print(f"[HIBP] Error {resp.status_code}, continuing...")
            return []
        
        breaches = resp.json()
        results = []
        for breach in breaches:
            results.append({
                "name": breach.get("Name", ""),
                "date": breach.get("BreachDate", ""),
                "data_classes": ", ".join(breach.get("DataClasses", []))
            })
        
        print(f"[HIBP] Found {len(results)} breaches")
        return results
        
    except Exception as e:
        print(f"[HIBP] Error: {e}, continuing...")
        return []


def enrich_shodan(ip: str) -> Optional[Dict]:
    """
    Shodan - IP/Host lookup - 100 free/month
    """
    api_key = get_key("shodan")
    if not api_key:
        return None
    
    print(f"[SHODAN] Looking up IP: {ip}")
    
    try:
        resp = requests.get(
            f"https://api.shodan.io/shodan/host/{ip}",
            params={"key": api_key},
            timeout=15
        )
        
        if resp.status_code != 200:
            print(f"[SHODAN] Error {resp.status_code}, continuing...")
            return None
        
        data = resp.json()
        print(f"[SHODAN] Found data for {ip}")
        return {
            "ip": ip,
            "hostnames": data.get("hostnames", []),
            "org": data.get("org", ""),
            "country": data.get("country_name", ""),
            "ports": data.get("ports", [])
        }
        
    except Exception as e:
        print(f"[SHODAN] Error: {e}, continuing...")
        return None


def enrich_fullcontact(email: str) -> Optional[Dict]:
    """
    FullContact - Person enrichment by email
    """
    api_key = get_key("fullcontact")
    if not api_key:
        return None
    
    print(f"[FULLCONTACT] Looking up: {email}")
    
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        resp = requests.post(
            "https://api.fullcontact.com/v3/person.enrich",
            headers=headers,
            json={"email": email},
            timeout=15
        )
        
        if resp.status_code != 200:
            print(f"[FULLCONTACT] Error {resp.status_code}, continuing...")
            return None
        
        data = resp.json()
        print(f"[FULLCONTACT] Found profile data")
        return {
            "name": data.get("fullName", ""),
            "location": data.get("location", ""),
            "bio": data.get("bio", ""),
            "social_profiles": data.get("socialProfiles", [])
        }
        
    except Exception as e:
        print(f"[FULLCONTACT] Error: {e}, continuing...")
        return None


def search_social_searcher(query: str) -> List[Dict[str, str]]:
    """
    Social Searcher - Public social media posts - 100 free/day
    """
    api_key = get_key("social_searcher")
    if not api_key:
        return []
    
    print(f"[SOCIAL SEARCHER] Searching: {query}")
    
    try:
        resp = requests.get(
            "https://api.social-searcher.com/v2/search",
            params={
                "q": query,
                "key": api_key,
                "limit": 20
            },
            timeout=15
        )
        
        if resp.status_code != 200:
            print(f"[SOCIAL SEARCHER] Error {resp.status_code}, continuing...")
            return []
        
        data = resp.json()
        results = []
        for post in data.get("posts", []):
            results.append({
                "network": post.get("network", ""),
                "user": post.get("user", {}).get("name", ""),
                "text": post.get("text", "")[:300],
                "url": post.get("url", "")
            })
        
        print(f"[SOCIAL SEARCHER] Found {len(results)} posts")
        return results
        
    except Exception as e:
        print(f"[SOCIAL SEARCHER] Error: {e}, continuing...")
        return []
