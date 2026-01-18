from typing import TypedDict, List, Optional, Set
from langgraph.graph import StateGraph, END
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage
import sys
import os
import time
import asyncio
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

class TimelineEvent(TypedDict):
    """A point in time for the target's life."""
    date: str
    event: str
    source_url: str

class AgentState(TypedDict):
    """The working memory of the demon."""
    messages: List[BaseMessage]
    profile: TargetProfile
    
    # Snowball Logic State
    gathered_data: List[SourceItem] # All confirmed relevant data
    search_queue: List[str] # Queries waiting to be executed
    visited_queries: List[str] # Queries strictly already executed
    visited_urls: List[str] # URLs already fetched to avoid cycles
    
    # Advanced Intelligence
    timeline_events: List[TimelineEvent]
    connections: List[str] # Mutual friends / frequent associations
    found_identifiers: List[str] # Confirmed unique IDs (e.g., license numbers, specific ID strings)
    
    depth: int # Current recursion depth
    max_depth: int # Max recursion limit
    
    hypocrisy_score: float

# --- 2. Nodes (The Actions) ---
# FIX #1: Add validate_query helper function
def validate_query(query: str) -> bool:
    """Validate that a query is suitable for search."""
    if not query or not isinstance(query, str):
        return False
    q_stripped = query.strip()
    if len(q_stripped) < 2:
        return False
    # Reject queries with only special characters or numbers
    if not any(c.isalnum() for c in q_stripped):
        return False
    return True

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
        "timeline_events": [],
        "connections": [],
        "found_identifiers": [],
        "depth": 0,
        "max_depth": 5
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
    
    # PRIMARY keywords (Must have at least one of these)
    name_parts = name.lower().split()
    primary_keywords = name_parts.copy()
    primary_keywords.append(name.lower())
    
    if profile.get("nickname"): primary_keywords.append(profile["nickname"].lower())
    if profile.get("phone"):
        phone = profile["phone"]
        primary_keywords.append(phone)
        primary_keywords.append(phone.replace("+", "").replace(" ", "").replace("-", ""))
    
    
    print(f"\n[SEARCH NODE] Depth: {state.get('depth')} | Queue Size: {len(queue)}")
    
    new_items: List[SourceItem] = []
    queries_to_run_actual = []
    is_pivot_search = False
    
    for q in queue:
        if q not in visited_q:
            # FIX #1: Validate query before adding to run list
            if not validate_query(q):
                visited_q.append(q)
                continue
            
            # If the query DOES NOT contain the target's primary name, it's a pivot
            if profile["name"].lower() not in q.lower():
                is_pivot_search = True
            
            queries_to_run_actual.append(q)
            visited_q.append(q)
            if len(queries_to_run_actual) >= 10:
                break
    
    if not queries_to_run_actual:
        print("[SEARCH] No new queries to run.")
        return {"search_queue": []}
    
    # 2. Parallel Search and Fetch
    search_tasks = []
    for q in queries_to_run_actual:
        print(f"[SEARCH] Hunting: {q}")
        search_tasks.append(asyncio.to_thread(perform_search, q, max_results=20))
    
    search_results = await asyncio.gather(*search_tasks)
    
    all_links = []
    for results in search_results:
        all_links.extend(results)
    
    # Deduplicate links by URL across all queries
    unique_links = []
    seen_step_urls = set()
    for link in all_links:
        u = link["href"]
        if u not in visited_u and u not in seen_step_urls:
            unique_links.append(link)
            seen_step_urls.add(u)
    
    # Batch fetch pages
    async def safe_fetch(link):
        url = link["href"]
        title = link["title"] or ""
        print(f"[FETCH] Downloading: {title[:60]}...")
        try:
            clean_text = await fetch_dynamic_page(url)
            if clean_text and len(clean_text) >= 100:
                return {"title": title, "url": url, "text": clean_text}
        except Exception as e:
            print(f"[FETCH ERROR] {url}: {e}")
        return None

    fetch_tasks = [safe_fetch(link) for link in unique_links[:30]] # Limit to 30 concurrent fetches per step
    fetched_pages = await asyncio.gather(*fetch_tasks)
    
    for page in fetched_pages:
        if not page: continue
        
        url = page["url"]
        title = page["title"]
        clean_text = page["text"]
        lower_text = clean_text.lower()
        
        # Identity match
        text_match_primary = any(k in lower_text for k in primary_keywords if k)
        url_match_primary = any(k in url.lower() for k in primary_keywords if k)
        
        # SIMPLE FILTER LOGIC
if not (text_match_primary or url_match_primary):
            print(f"[FILTER] Dropped {url[:40]} - No identity match.")
            continue
        
        print(f"[FETCH] ACCEPTED: {url[:60]}")
        item: SourceItem = {
            "title": title[:200],
            "url": url,
            "snippet": clean_text[:15000] # Slightly increased snippet
        }
        new_items.append(item)
        visited_u.add(url)
    
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
    
    context = "\n".join([f"SOURCE {i}: {d['title']}\n{d['snippet'][:4000]}\n" for i, d in enumerate(data)])
    
    # FIX #3: IMPROVED EXTRACTION PROMPT with better constraints
    # Added stricter validation rules to prevent hallucination
    prompt = f"""You are an OSINT Hunter. Extract ONLY valuable and VERIFIED pivots, events, and connections.
Looking for:
1. Email addresses, handles, phone numbers - MUST be explicitly mentioned in the source text.
2. TIMELINE EVENTS: Dates or years associated with the target (birth, graduation, job change, photo uploads).
3. CONNECTIONS: Names of people EXPLICITLY mentioned as connected to the target (friends, relatives, colleagues).
4. Profession/Job and geographic locations.

Context:
{context}

Return JSON:
{{
 "new_search_queries": [ {{ "query": "...", "confidence": 1-10, "reason": "..." }} ],
 "timeline_events": [ {{ "date": "...", "event": "...", "source_url": "..." }} ],
 "key_connections": [ {{ "name": "...", "confidence": 1-10 }} ],
 "found_identifiers": ["unique_id_or_number"],
 "profession": "if found"
}}

Rules (CRITICAL - MUST FOLLOW):
1. ONLY add search queries for specific people/entities EXPLICITLY MENTIONED AS BEING CONNECTED to the target.
2. High confidence (8-10) only if the source directly states the connection (e.g. 'friend of', 'CEO of', 'spouse of').
3. Extraction must be STRICT. If it looks like a different person with a similar name, DROP IT. DO NOT GUESS.
4. If you cannot find a piece of information in the provided context, DO NOT INVENT IT.
5. Never extract information from generic statements or assumptions. Only extract facts explicitly stated in sources.
6. Validate every connection: Does the source actually say this person is connected to the target?
"""
    
    try:
        res = llm.invoke([HumanMessage(content=prompt)])
        import json
        try:
            parsed = json.loads(res.content)
            
            new_qs_data = parsed.get("new_search_queries", [])
            new_events = parsed.get("timeline_events", [])
            new_conns_data = parsed.get("key_connections", [])
            new_ids = parsed.get("found_identifiers", [])
            
            print(f"[EXTRACTION] Found {len(new_qs_data)} potential queries, {len(new_events)} events.")
            
            current_q = state.get("search_queue", [])
            visited_q = state.get("visited_queries", [])
            final_q = current_q
            
            # --- FIX: Removed hardcoded blacklist ---
            blacklist = []
            # ----------------------------------------
            
            for q_obj in new_qs_data:
                q = q_obj.get("query", "") if isinstance(q_obj, dict) else q_obj
                conf = q_obj.get("confidence", 0) if isinstance(q_obj, dict) else 10
                
                if isinstance(q, str) and q.strip() and conf >= 7:
                    q_lower = q.lower()
                    if len(q_lower) < 3 or q_lower in visited_q or q in current_q:
                        continue
                    final_q.append(q)
            
            # Combine and deduplicate
            events = state.get("timeline_events", []) + new_events
            
            connections = state.get("connections", [])
            for c in new_conns_data:
                c_name = c.get("name") if isinstance(c, dict) else c
                c_conf = c.get("confidence", 0) if isinstance(c, dict) else 10
                if c_name and c_conf >= 7 and c_name not in connections:
                    connections.append(c_name)
            
            ids = list(set(state.get("found_identifiers", []) + new_ids))
            
            return {
                "search_queue": final_q, 
                "timeline_events": events,
                "connections": connections,
                "found_identifiers": ids,
                "depth": depth + 1
            }
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
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
"""
    
    sources_str = ""
    for i, item in enumerate(data, start=1):
        sources_str += f"\nSOURCE {i} ({item['title']}):\n{item['url']}\n{item['snippet'][:5000]}\n---\n"
    
    timeline_str = "\n".join([f"- {e['date']}: {e['event']} (Source: {e['source_url']})" for e in state.get("timeline_events", [])])
    connections_str = ", ".join(state.get("connections", []))
    
    prompt = f"""You are a STRICT OSINT DATA ANALYST for the Bakasura Protocol.
{target_section}
EVIDENCE COLLECTED:
{sources_str}
EXTRACTED TIMELINE:
{timeline_str}
SOCIAL CONNECTIONS:
{connections_str}
FOUND UNIQUE IDENTIFIERS:
{state.get('found_identifiers', [])}
TASK: Build a confirmed digital dossier.
ENTITY RESOLUTION IS CRITICAL: Do not merge multiple people with the same name.
HARD RULES:
1. JSON output only.
2. "is_person_found": boolean.
3. "verified_facts": [ {{ "fact": "...", "source": "url", "confidence": 1-10 }} ] - Only facts confirmed to belong to the target.
4. "potential_matches_noise": [ {{ "description": "...", "source": "url", "reason_for_doubt": "..." }} ] - Data for people with the same name that likely ARE NOT the target.
5. "digital_footprint": {{ "emails", "phones", "social_links", "handles" }}.
6. "timeline": [ {{ "date", "event", "source" }} ].
7. "notes": "Summary of the findings and reliability of data."
ENTITY RESOLUTION LOGIC:
- If a source mentions a different location (e.g. Voronezh vs Barnaul) or birthdate without a clear reason, move it to 'potential_matches_noise'.
- If a unique identifier (Phone, Email, ID number) matches perfectly, mark as high confidence.
- Be very skeptical of common name matches in Wikipedia or Discogs unless a direct link (phone/city/face) is found.
Analyze now."""
    
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        return {"messages": state.get("messages", []) + [response]}
    except Exception as e:
        return {"messages": state.get("messages", []) + [SystemMessage(content=f"Error: {e}")]}


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
        return {} # Skip if no data
    
    # Combine all text for deep analysis
    # Combine more text for deeper analysis
    all_text = ""
    for i, d in enumerate(data[:20]): # Increased to 20 sources
        all_text += f"SOURCE_ID_{i}: {d['title']}\nURL: {d['url']}\nCONTENT: {d['snippet'][:6000]}\n===\n"
    
    prompt = f"""You are an EXPERT CRIMINOLOGIST and PSYCHOLOGICAL PROFILER.
Analyze the following OSINT data about: {profile.get('name', 'Unknown')}
COLLECTED DATA:
{all_text[:80000]}
TASK: 
Create a nuanced psychological profile.
CRITICAL RULE: For EVERY observation, you MUST provide a "source_evidence" string explaining exactly which source and what text led to this conclusion.
Rules to avoid bias:
1. Do NOT confuse the nature of the website (e.g., social media aggregator) with the person's personality.
2. Having a social media profile or photos is NORMAL, not "exhibitionism" or "attention-seeking" unless the content itself is extreme or overtly suggestive.
3. Be respectful and objective. If no data exists for a field, state "Insufficient data".
Return JSON with these fields:
{{
 "personality_type": {{ "value": "description", "source_evidence": "quote or citation" }},
 "interests": [ {{ "item": "name", "source_evidence": "..." }} ],
 "communication_style": {{ "value": "...", "source_evidence": "..." }},
 "values": [ {{ "item": "...", "source_evidence": "..." }} ],
 "intelligence_markers": {{ "value": "...", "source_evidence": "..." }},
 "emotional_patterns": {{ "value": "...", "source_evidence": "..." }},
 "social_behavior": {{ "value": "...", "source_evidence": "..." }},
 "consistency": {{ "value": "...", "source_evidence": "..." }},
 "red_flags": [ {{ "flag": "...", "source_evidence": "..." }} ],
 "positive_traits": [ {{ "trait": "...", "source_evidence": "..." }} ],
 "summary": "Overall impression based ONLY on the evidence above."
}}
"""
    
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        import json
        try:
            personality_data = json.loads(response.content)
            
            # Try to find the dossier in previous messages
            messages = state.get("messages", [])
            dossier = {}
            if messages:
                content = messages[-1].content
                try:
                    # Strip markdown if needed
                    clean_json = content
                    if "```json" in content:
                        clean_json = content.split("```json")[-1].split("```").strip()
                    elif "```" in content:
                        clean_json = content.split("```")[-2].strip()
                    dossier = json.loads(clean_json)
                except: pass
            
            if dossier and isinstance(dossier, dict):
                # MERGE: Add personality to the main report
                dossier["personality_analysis"] = personality_data
                return {"messages": messages + [SystemMessage(content=json.dumps(dossier, ensure_ascii=False))]}
            else:
                # Fallback: Just return personality
                profile_msg = f"PERSONALITY PROFILE (WITH EVIDENCE):\n{json.dumps(personality_data, indent=2, ensure_ascii=False)}"
                return {"messages": messages + [SystemMessage(content=profile_msg)]}
        except:
            return {"messages": state.get("messages", []) + [response]}
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
workflow.add_node("personality", personality_node) # NEW!
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
