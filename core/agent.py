from typing import TypedDict, List, Optional, Set
from langgraph.graph import StateGraph, END
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage
import sys
import os
import time

# Ensure we can import our rust extension (Optional backup)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# IMPORT NEW SCRAPER
from scraper import fetch_dynamic_page
from search_tool import perform_search
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

    # Defaults
    return {
        "messages": [SystemMessage(content=f"Target Locked: {name}. Initiating Snowball Protocol.")],
        "search_queue": initial_queries,
        "visited_queries": [],
        "visited_urls": [],
        "gathered_data": [],
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
    
    new_items: List[SourceItem] = []
    
    queries_to_run = []
    for q in queue:
        if q not in visited_q:
            queries_to_run.append(q)
            visited_q.append(q)
        if len(queries_to_run) >= 5: # INCREASED: Batch size 5
            break
            
    if not queries_to_run:
        print("[SEARCH] No new queries to run.")
        return {"search_queue": []}

    for q in queries_to_run:
        print(f"[SEARCH] Hunting: {q}")
        links = perform_search(q, max_results=10) # INCREASED: 10 results per query
        
        for link in links:
            url = link["href"]
            title = link["title"] or ""
            
            if url in visited_u:
                continue
            visited_u.add(url)
            
            print(f"[FETCH] Downloading (Playwright): {title[:60]}...")
            print(f"[FETCH] Downloading (Playwright): {title[:60]}...")
            try:
                # USE NEW SCRAPER - ASYNC WAIT
                clean_text = await fetch_dynamic_page(url)
                
                if not clean_text or len(clean_text) < 100:
                    print(f"[FETCH FAIL] Empty/Short content from {url}")
                    continue
                
                # Cleanup whitespace just in case
                clean_text = " ".join(clean_text.split())
                lower_text = clean_text.lower()
                
                # PRE-FILTER
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
                    "snippet": clean_text[:15000]  # INCREASED for deeper analysis
                }
                new_items.append(item)
                
            except Exception as e:
                print(f"[FETCH ERROR] {e}")

    total_data = gathering + new_items
    remaining_queue = [q for q in queue if q not in visited_q]
    
    return {
        "gathered_data": total_data,
        "visited_urls": list(visited_u),
        "visited_queries": visited_q,
        "search_queue": remaining_queue 
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
        return {}

    llm = ChatOllama(model="llama3.1", format="json")
    
    context = "\n".join([f"SOURCE {i}: {d['title']}\n{d['snippet'][:800]}\n" for i, d in enumerate(data)])
    
    prompt = f"""You are an OSINT Hunter. Extract ALL valuable pivots from these data sources.

Looking for:
1. Email addresses
2. Usernames/handles (VK, Skype, Telegram, Instagram, Facebook)
3. Phone numbers
4. Profession/Job (psychologist, developer, etc.)
5. Friends/Contacts names (especially from VK mirror sites like ru-world.net, profiles-vkontakte.ru, gomelin.com)
6. Interests, hobbies, books, music (for personality profiling)
7. Education, workplace info
8. Geographic locations (cities where friends live)

Context:
{context}

Return JSON:
{{
  "new_search_queries": ["query1", "query2"],
  "extracted_contacts": ["contact1", "contact2"],
  "extracted_handles": ["@handle1", "skype:xxx"],
  "profession": "if found",
  "key_friends": ["friend names that appear frequently"]
}}

Rules:
1. Queries must be specific.
2. If you see VK friends list, extract top frequent names for "mutual connections" research.
3. If profession found, create query like '"Name" profession city'.
4. Extract Skype, VK handle if visible.
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
    llm = ChatOllama(model="llama3.1", format="json")
    profile = state["profile"]
    data = state.get("gathered_data", [])

    if not data:
        return {"messages": [SystemMessage(content="No data found.")]}

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


async def personality_node(state: AgentState):
    """
    BONUS: Psychological profile based on gathered content.
    Analyzes communication style, interests, red flags.
    """
    print("--- PERSONALITY ANALYSIS ---")
    llm = ChatOllama(model="llama3.1", format="json")
    profile = state["profile"]
    data = state.get("gathered_data", [])
    
    if not data:
        return {}  # Skip if no data
    
    # Combine all text for deep analysis
    all_text = "\n\n".join([
        f"=== SOURCE: {d['title']} ===\n{d['snippet'][:5000]}" 
        for d in data[:5]  # Top 5 sources
    ])
    
    prompt = f"""You are a PSYCHOLOGICAL PROFILER. Analyze the following content about this person:

TARGET: {profile.get('name', 'Unknown')}

COLLECTED CONTENT:
{all_text[:20000]}

Create a psychological profile. Return JSON with these fields:

{{
  "personality_type": "Brief description (e.g., 'Extrovert, creative, ambitious')",
  "interests": ["list", "of", "interests"],
  "communication_style": "How they express themselves",
  "values": ["what they seem to value"],
  "intelligence_markers": "Observations about intellect/education",
  "emotional_patterns": "Emotional tendencies observed",
  "social_behavior": "How they interact with others",
  "consistency": "Are their statements/views consistent?",
  "red_flags": ["Any concerning patterns or inconsistencies"],
  "positive_traits": ["Notable positive characteristics"],
  "summary": "2-3 sentence overall impression"
}}

Be objective. Base conclusions ONLY on evidence in the text. If unsure, say so."""

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        # Store in messages for frontend
        import json
        try:
            parsed = json.loads(response.content)
            # Create a formatted message for display
            profile_msg = f"PERSONALITY PROFILE:\n{json.dumps(parsed, indent=2, ensure_ascii=False)}"
            return {"messages": state.get("messages", []) + [SystemMessage(content=profile_msg)]}
        except:
            return {}
    except Exception as e:
        print(f"[PERSONALITY] Error: {e}")
        return {}


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
workflow.add_node("personality", personality_node)  # NEW!

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

# Chain: analyze -> personality -> END
workflow.add_edge("analyze", "personality")
workflow.add_edge("personality", END)

app = workflow.compile()

