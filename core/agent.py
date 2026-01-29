from typing import TypedDict, List, Optional, Set
from langgraph.graph import StateGraph, END
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage
import sys
import os
import time

# Ensure we can import our rust extension (Optional backup)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json

from scraper import fetch_dynamic_page
from search_tool import perform_search
from flowsint_tool import search_username_with_maigret
from bs4 import BeautifulSoup

# --- 1. State Definition (The Memory) ---

class TargetProfile(TypedDict):
    """The 'Dead Data' provided by the user."""
    name: str
    city: Optional[str]
    country: Optional[str]
    phone: Optional[str]
    nickname: Optional[str]
    other_clues: Optional[str]

class SourceItem(TypedDict):
    """A single piece of gathered intelligence."""
    title: str
    url: str
    snippet: str

class AgentState(TypedDict):
    """The working memory of the demon."""
    messages: List[BaseMessage]
    profile: TargetProfile
    
    # Snowball Logic State
    gathered_data: List[SourceItem]  # All confirmed relevant data
    search_queue: List[str]          # Queries waiting to be executed
    url_queue: List[str]             # URLs waiting to be fetched directly
    visited_queries: List[str]       # Queries strictly already executed
    visited_urls: List[str]          # URLs already fetched to avoid cycles
    
    depth: int                       # Current recursion depth
    max_depth: int                   # Max recursion limit
    
    hypocrisy_score: float

# --- 2. Nodes (The Actions) ---

async def input_validation_node(state: AgentState):
    """
    Initializes the hunt. Populates the first search queries.
    """
    profile = state["profile"]
    if not profile.get("name"):
        return {"messages": [SystemMessage(content="[ERROR] I need a Name to start hunting.")]}
    
    # Init Snowball State
    name = profile["name"]
    city = profile.get("city") or ""
    nick = profile.get("nickname") or ""
    phone = profile.get("phone") or ""
    
    initial_queries = []
    
    # Base queries
    base = f'"{name}"'
    if city:
        base += f' "{city}"'
    initial_queries.append(base)
    
    if nick:
        initial_queries.append(f'"{nick}" profile')
        initial_queries.append(f'"{nick}" "{name}"')
        
    if phone:
        initial_queries.append(f'"{phone}"')

    # --- LOAD MIRRORS ---
    try:
        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "mirrors.json")
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                mirrors_config = json.load(f)
                if mirrors_config.get("enable_mirrors", False):
                    mirrors = mirrors_config.get("social_mirrors", [])
                    print(f"[INIT] Loaded {len(mirrors)} priority mirrors.")
                    for m in mirrors:
                        # Add specific site searches
                        # e.g. site:picuki.com "Target Name"
                        initial_queries.insert(0, f'site:{m} "{name}"')
                        if nick:
                             initial_queries.insert(0, f'site:{m} "{nick}"')
    except Exception as e:
        print(f"[INIT] Failed to load mirrors: {e}")

    # --- MAIGRET INTEGRATION ---
    maigret_data = []
    maigret_urls = []
    
    if nick and len(nick) > 3:
         print(f"[INIT] Launching Maigret social scan for '{nick}'...")
         try:
             # Run Maigret (this may take time)
             m_results = await search_username_with_maigret(nick)
             for item in m_results:
                 maigret_data.append({
                     "title": item["title"],
                     "url": item["url"],
                     "snippet": item["snippet"]
                 })
                 maigret_urls.append(item["url"])
         except Exception as e:
             print(f"[INIT] Maigret failed: {e}")

    # Defaults
    return {
        "messages": [SystemMessage(content=f"Target Locked: {name}. Initiating Snowball Protocol.")],
        "search_queue": initial_queries,
        "url_queue": maigret_urls,
        "visited_queries": [],
        "visited_urls": [],
        "gathered_data": maigret_data,
        "depth": 0,
        "max_depth": 3  # INCREASED: Allows 3 rounds of expansion
    }


async def search_node(state: AgentState):
    """
    Consumes the ENTIRE search queue for this step.
    Searches, fetches (PLAYWRIGHT), cleans, and filters.
    """
    queue = state.get("search_queue", [])
    visited_q = state.get("visited_queries", [])
    visited_u = set(state.get("visited_urls", []))
    gathering = state.get("gathered_data", [])
    
    profile = state["profile"]
    name = profile["name"]
    
    # Strict filter keywords
    filter_keywords = [name.lower()]
    if profile.get("nickname"): filter_keywords.append(profile["nickname"].lower())
    if profile.get("phone"): filter_keywords.append(profile["phone"])
    
    print(f"\n[SEARCH NODE] Depth: {state.get('depth')} | Queue Size: {len(queue)}")
    
    def is_garbage_url(url: str, title: str, profile: TargetProfile) -> bool:
        """Face control for URLs to avoid obvious noise."""
        bad_domains = [
            "yandex.ru/maps", "google.com/search", 
            "wikipedia.org", "bigenc.ru"
        ]
        
        # Filter out API endpoints usually found in search results
        if "api." in url.lower() or "typeahead" in url.lower() or "opensearch" in url.lower():
             return True
        
        url_lower = url.lower()
        title_lower = title.lower()
        
        # 1. Domain Blacklist
        if any(d in url_lower for d in bad_domains):
            return True
        
        # 2. Strict Nickname Match (Avoid 'solomontaiwo' if looking for 'solomoon')
        target_nick = profile.get("nickname", "").lower()
        if target_nick:
            # If a common variant like 'solomon' is in URL, but NOT our specific nick
            if "solomon" in url_lower and target_nick not in url_lower:
                return True
            # Case for general nick mismatch in URL path
            if "/" + target_nick not in url_lower and target_nick in url_lower:
                 # Check if it was just a substring of another word
                 import re
                 if not re.search(rf"\b{re.escape(target_nick)}\b", url_lower):
                     return True

        return False

    # Poison keywords that indicate we found a different person (e.g. a famous gymnast)
    poison_keywords = ["gymnast", "olympic", "medalist", "died", "born 1929", "ussr", "champion", "athlete"]

    new_items: List[SourceItem] = []
    
    queries_to_run = []
    for q in queue:
        if q not in visited_q:
            queries_to_run.append(q)
            visited_q.append(q)
        if len(queries_to_run) >= 5: # INCREASED: Batch size 5
            break
            
    # Also consume URL queue
    url_queue = state.get("url_queue", [])
    
    if not queries_to_run and not url_queue:
        print("[SEARCH] No new queries or URLs to run.")
        return {"search_queue": [], "url_queue": []}

    for q in queries_to_run:
        print(f"[SEARCH] Hunting: {q}")
        links = perform_search(q, max_results=10) # INCREASED: 10 results per query
        
        # Merge url_queue into links for the first query iteration (or just process them)
        if url_queue:
            print(f"[SEARCH] Injecting {len(url_queue)} direct URLs from queue...")
            for u in url_queue:
                links.append({"href": u, "title": "Direct URL Target"})
            url_queue = [] # Consumed
            
        for link in links:
            url = link["href"]
            title = link["title"] or ""
            
            if url in visited_u:
                continue
            
            # 1. PRE-FILTER (URL FAKECONTROL)
            if is_garbage_url(url, title, profile):
                print(f"[SKIP] Garbage URL: {url[:60]}...")
                visited_u.add(url) # Don't revisit garbage
                continue

            visited_u.add(url)
            
            print(f"[FETCH] Downloading (Playwright): {title[:60]}...")
            try:
                # USE NEW SCRAPER - ASYNC WAIT
                clean_text = await fetch_dynamic_page(url)
                
                if not clean_text or len(clean_text) < 100:
                    print(f"[FETCH FAIL] Empty/Short content from {url}")
                    continue
                
                # Cleanup whitespace
                clean_text = " ".join(clean_text.split())
                lower_text = clean_text.lower()
                
                # 2. POISON FILTER (Tezka Check)
                is_poisoned = any(pk in lower_text for pk in poison_keywords)
                if is_poisoned:
                    print(f"[POISON] Dropped {url[:40]} - Contains poison keywords (Tezka detected).")
                    continue

                # 3. IDENTITY FILTER
                # Relaxed: Check Text OR URL for identity match
                text_match = any(k in lower_text for k in filter_keywords if k)
                url_match = any(k in url.lower() for k in filter_keywords if k)
                
                if not (text_match or url_match):
                    print(f"[FILTER] Dropped {url[:40]} - No identity match in Text or URL.")
                    continue
                    
                print(f"[FETCH] ACCEPTED: {url[:60]}")
                item: SourceItem = {
                    "title": title[:200],
                    "url": url,
                    "snippet": clean_text[:6000] # Increased cap
                }
                new_items.append(item)
                
            except Exception as e:
                print(f"[FETCH ERROR] {e}")

    total_data = gathering + new_items
    print(f"[SEARCH NODE] Finished search. Collected {len(new_items)} NEW items. Total items: {len(total_data)}")
    remaining_queue = [q for q in queue if q not in visited_q]
    
    return {
        "gathered_data": total_data,
        "visited_urls": list(visited_u),
        "visited_queries": visited_q,
        "visited_queries": visited_q,
        "search_queue": remaining_queue,
        "url_queue": [] # Clear consumed URLs
    }


async def extraction_node(state: AgentState):
    """
    Analyzes gathered data to find NEW Pivots.
    """
    print("[EXTRACTION] Looking for new pivots...")
    depth = state.get("depth", 0)
    max_depth = state.get("max_depth", 1)
    
    if depth >= max_depth:
        print("[EXTRACTION] Max depth reached. Skipping pivot extraction.")
        return {} 
        
    data = state.get("gathered_data", [])
    if not data:
        print("[EXTRACTION] No data found yet. Skipping pivot extraction for this round.")
        return {"depth": depth + 1}

    llm = ChatOllama(model="qwen2.5:14b", format="json")
    
    context = "\n".join([f"SOURCE {i}: {d['title']}\n{d['snippet'][:800]}\n" for i, d in enumerate(data)])
    
    prompt = f"""You are a Hunter. extract explicit OSINT pivots from these snippets.
Looking for: Email addresses, specific Usernames (handles), Phone numbers, unique identifiers, OR CURRENT OCCUPATION/JOB TITLE.
Context:
{context}

Return JSON:
{{
  "new_search_queries": ["query1", "query2"]
}}
Rules:
1. Queries must be specific.
2. Do NOT repeat the target's name if you didn't find a new specific identifier.
3. If you see a new profession/job (e.g., "Psychologist", "Photographer"), create a query for it (e.g., '"Name" Psychologist').
"""
    try:
        res = llm.invoke([HumanMessage(content=prompt)])
        import json
        try:
            parsed = json.loads(res.content)
            new_qs = parsed.get("new_search_queries", [])
            print(f"[EXTRACTION] Found {len(new_qs)} new pivots: {new_qs}")
            
            current_q = state.get("search_queue", [])
            visited_q = state.get("visited_queries", [])
            
            final_q = current_q
            for q in new_qs:
                # Sanitize: Ensure q is a string
                if isinstance(q, dict):
                    q = q.get("query") or str(q)
                if not isinstance(q, str):
                    q = str(q)
                    
                if q not in visited_q and q not in current_q:
                    final_q.append(q)
            
            return {"search_queue": final_q, "depth": depth + 1}
            
        except:
            return {"depth": depth + 1}
    except Exception as e:
        return {"depth": depth + 1}


async def analyze_node(state: AgentState):
    """
    FINAL Step: Produce the dossier from ALL gathered data.
    """
    print("--- FINAL ANALYSIS ---")
    llm = ChatOllama(model="qwen2.5:14b", format="json")
    profile = state["profile"]
    data = state.get("gathered_data", [])
    if not data:
        print("[ANALYZE] WARNING: No data collected in the entire hunt.")
        return {"messages": [SystemMessage(content="No relevant data was found for this target after multiple search rounds.")]}
    
    print(f"[ANALYZE] Processing {len(data)} items to generate final dossier...")

    # REINFORCED PROMPT
    target_section = f"""
!!! TARGET PROFILE - FOCUS ON THIS !!!
Name: {profile.get('name', 'Unknown')}
Location: {profile.get('city', 'Unknown')}, {profile.get('country', 'Unknown')}
Phone: {profile.get('phone', 'Unknown')}
Nickname: {profile.get('nickname', 'Unknown')}
Additional Clues: {profile.get('other_clues', 'Unknown')}
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
"""
    sources_str = ""
    for i, item in enumerate(data, start=1):
        sources_str += f"\nSOURCE {i} ({item['title']}):\n{item['url']}\n{item['snippet'][:1000]}\n---\n"

    prompt = f"""You are a STRICT DATA ANALYST.
{target_section}

EVIDENCE COLLECTED:
{sources_str}

TASK: Build a confirmed dossier.
HARD RULES:
1. JSON output only.
2. "is_person_found": boolean.
3. "matched_sources": list of dicts {{ "title", "url", "reason" }}.
4. "facts": list of strings.
5. "uncertain": list of strings.
6. "notes": string.

Analyze now."""

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        return {"messages": [response]}
    except Exception as e:
        return {"messages": [SystemMessage(content=f"Error: {e}")]}


def check_loop_condition(state: AgentState):
    queue = state.get("search_queue", [])
    depth = state.get("depth", 0)
    max_d = state.get("max_depth", 1)
    
    if queue and depth < max_d:
        print(">>> LOOPING: New queries in queue. Continuing hunt.")
        return "loop"
    
    print(">>> COMPLETE: Queue empty or max depth reached.")
    return "finish"

# --- 3. Graph Assembly ---
workflow = StateGraph(AgentState)

workflow.add_node("validate", input_validation_node)
workflow.add_node("search", search_node)
workflow.add_node("extract", extraction_node)
workflow.add_node("analyze", analyze_node)

workflow.set_entry_point("validate")

workflow.add_edge("validate", "search")
workflow.add_edge("search", "extract")

workflow.add_conditional_edges(
    "extract",
    check_loop_condition,
    {
        "loop": "search",
        "finish": "analyze"
    }
)

workflow.add_edge("analyze", END)

app = workflow.compile()
