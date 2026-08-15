from typing import TypedDict, List, Optional, Set, Tuple, Dict
from langgraph.graph import StateGraph, END
from langchain_cerebras import ChatCerebras
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage
import sys
import os
import re
import asyncio

# Ensure we can import our rust extension (Optional backup)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json

from scraper import fetch_page_sync
from search_tool import perform_search
from flowsint_tool import search_username_with_maigret
from pogoda_cse import search_pogoda_cse_sync
from tg_search import search_lyzem_sync
from getcontact_lookup import lookup_getcontact_sync
from vk_enrichment import extract_vk_id, enrich_vk_profile_sync
from enrichment import enrich_pivots, lookup_phone_free
from image_finder import extract_profile_image, reverse_search_yandex


def _parse_json_loose(text) -> dict:
    """Best-effort JSON parse - strips ```json fences if the LLM added them anyway."""
    if not isinstance(text, str):
        return {}
    cleaned = text.strip()
    if "```" in cleaned:
        cleaned = re.sub(r"```json|```", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        return {}


def score_confidence(text_lower: str, url_lower: str, profile: "TargetProfile") -> Tuple[float, List[str]]:
    """
    Weighted confidence score for a candidate source, replacing a flat boolean
    'name-or-nickname appears somewhere' check with something a downstream LLM (or
    a human) can actually triage by strength of evidence.
    """
    score = 0.0
    reasons: List[str] = []
    name = (profile.get("name") or "").lower()
    nick = (profile.get("nickname") or "").lower()
    phone = (profile.get("phone") or "").lower()
    city = (profile.get("city") or "").lower()
    country = (profile.get("country") or "").lower()

    if name and name in text_lower:
        score += 3; reasons.append("name in text")
    if nick and nick in text_lower:
        score += 3; reasons.append("nickname in text")
    if phone and phone in text_lower:
        score += 4; reasons.append("phone in text")
    if city and city in text_lower:
        score += 1; reasons.append("city in text")
    if country and country in text_lower:
        score += 0.5; reasons.append("country in text")
    if nick and nick in url_lower:
        score += 1; reasons.append("nickname in URL")

    if sum(1 for r in reasons if "in text" in r) >= 2:
        score += 1.5
        reasons.append("multiple independent signals")

    return round(score, 1), reasons

# --- 1. State Definition (The Memory) ---

class TargetProfile(TypedDict):
    """The 'Dead Data' provided by the user."""
    name: str
    city: Optional[str]
    country: Optional[str]
    phone: Optional[str]
    nickname: Optional[str]
    other_clues: Optional[str]

class SourceItem(TypedDict, total=False):
    """A single piece of gathered intelligence."""
    title: str
    url: str
    snippet: str
    confidence: float                # Weighted evidence score - see score_confidence()
    confidence_reasons: List[str]    # Which signals contributed to the score

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

    # Enrichment state (see enrich_node)
    processed_pivots: Dict[str, List[str]]  # emails/ips/domains already enriched - avoids repeat lookups
    profile_image_url: Optional[str]        # First profile photo found, for reverse-image search
    reverse_image_done: bool                # Reverse-image search only ever runs once per hunt
    phone_intel_done: bool                  # Offline phone lookup only ever runs once per hunt
    getcontact_done: bool                   # Getcontact web lookup only ever runs once per hunt
    vk_profiles_enriched: List[str]         # VK ids already run through 220vk/regvk - each done at most once
    image_checked_urls: List[str]           # URLs already probed for og:image - each checked at most once

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
                        # Add specific site searches AFTER the base identity queries
                        # (name/city/phone), so mirrors don't crowd them out of the
                        # first batches. e.g. site:picuki.com "Target Name"
                        initial_queries.append(f'site:{m} "{name}"')
                        if nick:
                             initial_queries.append(f'site:{m} "{nick}"')
    except Exception as e:
        print(f"[INIT] Failed to load mirrors: {e}")

    # --- RUPEP (RU/BY/KZ politically-exposed-persons database) ---
    # Just an ordinary indexed site, so a site: search is enough - no dedicated
    # integration needed, unlike the CSE/bot sources below.
    initial_queries.append(f'site:rupep.org "{name}"')

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
                     "snippet": item["snippet"],
                     "confidence": 1.5,
                     "confidence_reasons": ["Maigret claim - not yet content-verified"],
                 })
                 maigret_urls.append(item["url"])
         except Exception as e:
             print(f"[INIT] Maigret failed: {e}")

    # --- POGODA CSE (RU/CIS-scoped social search: VK/OK/Telegram/Dzen/etc.) ---
    try:
        cse_query = f"{name} {city}".strip() if city else name
        cse_results = await asyncio.to_thread(search_pogoda_cse_sync, cse_query, 10)
        for r in cse_results:
            if r["href"] not in maigret_urls:
                maigret_urls.append(r["href"])
    except Exception as e:
        print(f"[INIT] Pogoda CSE failed: {e}")

    # --- LYZEM (Telegram channel/group/bot name+bio search) ---
    try:
        lyzem_query = f"{name} {city}".strip() if city else name
        lyzem_results = await asyncio.to_thread(search_lyzem_sync, lyzem_query, 10)
        for r in lyzem_results:
            if r["href"] not in maigret_urls:
                maigret_urls.append(r["href"])
    except Exception as e:
        print(f"[INIT] Lyzem search failed: {e}")

    # Defaults
    return {
        "messages": [SystemMessage(content=f"Target Locked: {name}. Initiating Snowball Protocol.")],
        "search_queue": initial_queries,
        "url_queue": maigret_urls,
        "visited_queries": [],
        "visited_urls": [],
        "gathered_data": maigret_data,
        "depth": 0,
        "max_depth": 3,  # Allows 3 rounds of snowball expansion
        "processed_pivots": {"emails": [], "ips": [], "domains": []},
        "profile_image_url": None,
        "reverse_image_done": False,
        "getcontact_done": False,
        "vk_profiles_enriched": [],
        "image_checked_urls": [],
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
    
    def is_garbage_url(url: str, profile: TargetProfile) -> bool:
        """Face control for URLs to avoid obvious noise."""
        bad_domains = [
            "yandex.ru/maps", "google.com/search", 
            "wikipedia.org", "bigenc.ru"
        ]
        
        # Filter out API endpoints usually found in search results
        if "api." in url.lower() or "typeahead" in url.lower() or "opensearch" in url.lower():
             return True
        
        url_lower = url.lower()

        # 1. Domain Blacklist
        if any(d in url_lower for d in bad_domains):
            return True
        
        # 2. Strict Nickname Match (Avoid 'solomontaiwo' if looking for 'solomoon')
        target_nick = (profile.get("nickname") or "").lower()
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

    # Markers for dead/soft-404 pages. Sites like Maigret's target list frequently
    # return HTTP 200 with a generic "not found" template instead of a real 404 -
    # without this, a URL containing the target's nickname (e.g. every Maigret hit)
    # would pass the identity filter below purely on URL substring match, even when
    # the actual fetched page says the profile doesn't exist.
    dead_page_markers = [
        "page not found", "404 - page not found", "does not exist in our system",
        "user not found", "no such user", "account not found", "profile not found",
        "this page isn't available", "page isn't available", "user does not exist",
        "página não existe", "user tidak ditemukan", "tidak ditemukan",
        "не найден", "не найдена", "не существует", "страница не найдена",
        "аккаунт не найден", "пользователь не найден",
    ]

    def is_dead_page(text: str) -> bool:
        lower = text.lower()
        return any(marker in lower for marker in dead_page_markers)

    new_items: List[SourceItem] = []
    dead_urls: Set[str] = set()

    queries_to_run = []
    for q in queue:
        if q not in visited_q:
            queries_to_run.append(q)
            visited_q.append(q)
        if len(queries_to_run) >= 6: # Batch size per round
            break
            
    # Also consume URL queue
    url_queue = state.get("url_queue", [])
    
    if not queries_to_run and not url_queue:
        print("[SEARCH] No new queries or URLs to run.")
        return {"search_queue": [], "url_queue": []}

    for q in queries_to_run:
        print(f"[SEARCH] Hunting: {q}")
        links = await asyncio.to_thread(perform_search, q, 3)
        
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
            if is_garbage_url(url, profile):
                print(f"[SKIP] Garbage URL: {url[:60]}...")
                visited_u.add(url) # Don't revisit garbage
                continue

            visited_u.add(url)
            
            print(f"[FETCH] Downloading (Playwright): {title[:60]}...")
            try:
                # Run Playwright in its own thread+event loop so wait_for can cancel it
                clean_text = await asyncio.wait_for(
                    asyncio.to_thread(fetch_page_sync, url),
                    timeout=45.0
                )
                
                if not clean_text or len(clean_text) < 100:
                    print(f"[FETCH FAIL] Empty/Short content from {url}")
                    continue
                
                # Cleanup whitespace
                clean_text = " ".join(clean_text.split())
                lower_text = clean_text.lower()

                # 2. DEAD PAGE FILTER (soft-404 check)
                # Must run BEFORE the identity filter: a URL built from the target's
                # own nickname (e.g. every Maigret hit) will always "match" on URL
                # substring, so a dead/soft-404 page needs to be caught here or it
                # sails through as "confirmed" evidence regardless of content.
                if is_dead_page(lower_text):
                    print(f"[DEAD LINK] Dropped {url[:60]} - Page reports profile not found.")
                    dead_urls.add(url)
                    continue

                # 3. POISON FILTER (Tezka Check)
                is_poisoned = any(pk in lower_text for pk in poison_keywords)
                if is_poisoned:
                    print(f"[POISON] Dropped {url[:40]} - Contains poison keywords (Tezka detected).")
                    continue

                # 4. IDENTITY FILTER
                # Relaxed: Check Text OR URL for identity match
                text_match = any(k in lower_text for k in filter_keywords if k)
                url_match = any(k in url.lower() for k in filter_keywords if k)

                if not (text_match or url_match):
                    print(f"[FILTER] Dropped {url[:40]} - No identity match in Text or URL.")
                    continue
                    
                conf_score, conf_reasons = score_confidence(lower_text, url.lower(), profile)
                print(f"[FETCH] ACCEPTED: {url[:60]} (confidence {conf_score}: {', '.join(conf_reasons) or 'weak match'})")
                item: SourceItem = {
                    "title": title[:200],
                    "url": url,
                    "snippet": clean_text[:6000], # Increased cap
                    "confidence": conf_score,
                    "confidence_reasons": conf_reasons,
                }
                new_items.append(item)
                
            except Exception as e:
                print(f"[FETCH ERROR] {e}")

    # Drop any pre-existing entries (e.g. Maigret's canned "Match Confidence: High"
    # claims) whose URL we just confirmed to be a dead/soft-404 page above - a
    # claim about a URL shouldn't outlive proof that the URL doesn't resolve to
    # anything real.
    if dead_urls:
        before = len(gathering)
        gathering = [d for d in gathering if d["url"] not in dead_urls]
        print(f"[DEAD LINK] Purged {before - len(gathering)} stale claim(s) about confirmed-dead URLs.")

    total_data = gathering + new_items
    print(f"[SEARCH NODE] Finished search. Collected {len(new_items)} NEW items. Total items: {len(total_data)}")
    remaining_queue = [q for q in queue if q not in visited_q]

    return {
        "gathered_data": total_data,
        "visited_urls": list(visited_u),
        "visited_queries": visited_q,
        "search_queue": remaining_queue,
        "url_queue": [] # Clear consumed URLs
    }


async def enrich_node(state: AgentState):
    """
    Free enrichment pass, run after every search round:
      - Regex-extracts emails/IPs seen so far and fires HIBP/Hunter/Shodan/FullContact
        (all no-op without a key) plus WHOIS + offline phone lookup (always free).
      - One-shot reverse-image search via Yandex once we have a candidate profile photo.
    Never blocks the hunt - every source degrades to "found nothing" on failure.
    """
    profile = state["profile"]
    gathered = state.get("gathered_data", [])
    processed = state.get("processed_pivots") or {"emails": [], "ips": [], "domains": []}

    new_items, processed = await asyncio.to_thread(enrich_pivots, gathered, profile, processed)

    if profile.get("phone") and not state.get("phone_intel_done"):
        info = lookup_phone_free(profile["phone"])
        if info:
            new_items.append({
                "title": f"Phone Intel: {profile['phone']}",
                "url": "",
                "snippet": f"Region: {info.get('region')}. Carrier: {info.get('carrier')}. "
                           f"Type: {info.get('number_type')}. Valid E.164: {info.get('e164')}",
                "confidence": 5.0,
                "confidence_reasons": ["offline libphonenumber lookup - deterministic"],
            })

    if profile.get("phone") and not state.get("getcontact_done"):
        gc = await asyncio.to_thread(lookup_getcontact_sync, profile["phone"])
        if gc and gc.get("found"):
            new_items.append({
                "title": f"Getcontact: {profile['phone']}",
                "url": gc["url"],
                "snippet": gc.get("raw_text", ""),
                "confidence": 1.0,
                "confidence_reasons": ["Getcontact community data - unparsed page text, not yet content-verified"],
            })

    vk_enriched = set(state.get("vk_profiles_enriched") or [])
    new_vk_lookups = 0
    for item in gathered:
        if new_vk_lookups >= 3:  # cap browser launches per round - Pogoda CSE alone can surface many VK hits
            break
        vk_id = extract_vk_id(item.get("url", ""))
        if not vk_id or vk_id in vk_enriched:
            continue
        vk_enriched.add(vk_id)
        new_vk_lookups += 1
        print(f"[ENRICH] New VK profile '{vk_id}' found - running 220vk/regvk...")
        vk_data = await asyncio.to_thread(enrich_vk_profile_sync, vk_id)
        if vk_data.get("220vk"):
            new_items.append({
                "title": f"220vk activity history: vk.com/{vk_id}",
                "url": f"https://220vk.com/{vk_id}?i",
                "snippet": vk_data["220vk"][:2500],
                "confidence": 1.5,
                "confidence_reasons": ["220vk activity/friend-history data - not yet content-verified"],
            })
        if vk_data.get("regvk"):
            new_items.append({
                "title": f"regvk registration date: vk.com/{vk_id}",
                "url": "https://regvk.com/",
                "snippet": vk_data["regvk"][:1500],
                "confidence": 1.5,
                "confidence_reasons": ["regvk registration-date data - not yet content-verified"],
            })

    image_url = state.get("profile_image_url")
    reverse_done = state.get("reverse_image_done", False)
    checked_urls = set(state.get("image_checked_urls") or [])
    if not image_url and gathered:
        for item in gathered:
            u = item.get("url")
            if not u or u in checked_urls:
                continue
            checked_urls.add(u)
            img = await asyncio.to_thread(extract_profile_image, u)
            if img:
                image_url = img
                print(f"[ENRICH] Found candidate profile image: {img[:80]}")
                break

    if image_url and not reverse_done:
        print("[ENRICH] Running one-shot Yandex reverse image search...")
        hits = await asyncio.to_thread(reverse_search_yandex, image_url)
        for h in hits:
            new_items.append({
                "title": f"Reverse Image Hit: {h['title']}",
                "url": h["href"],
                "snippet": f"Page visually matches target's profile photo ({image_url}). "
                           f"UNVERIFIED - identity not text-confirmed, treat as a lead not a fact.",
                "confidence": 1.0,
                "confidence_reasons": ["visual similarity only - not text confirmed"],
            })
        reverse_done = True

    if new_items:
        print(f"[ENRICH] Added {len(new_items)} enrichment item(s).")

    return {
        "gathered_data": gathered + new_items,
        "processed_pivots": processed,
        "profile_image_url": image_url,
        "reverse_image_done": reverse_done,
        "phone_intel_done": True,
        "getcontact_done": True,
        "vk_profiles_enriched": list(vk_enriched),
        "image_checked_urls": list(checked_urls),
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

    llm = ChatCerebras(model="gpt-oss-120b").bind(response_format={"type": "json_object"})

    ranked = sorted(data, key=lambda d: -(d.get("confidence") or 0))
    context = "\n".join([f"SOURCE {i} [confidence {d.get('confidence', '?')}]: {d['title']}\n{d['snippet'][:800]}\n" for i, d in enumerate(ranked)])
    
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
        res = await llm.ainvoke([HumanMessage(content=prompt)])
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
    llm = ChatCerebras(model="gpt-oss-120b").bind(response_format={"type": "json_object"})
    profile = state["profile"]
    data = state.get("gathered_data", [])
    if not data:
        print("[ANALYZE] WARNING: No data collected in the entire hunt.")
        return {"messages": [SystemMessage(content="No relevant data was found for this target after multiple search rounds.")]}
    
    print(f"[ANALYZE] Processing {len(data)} items to generate final dossier...")

    # REINFORCED PROMPT
    target_section = f"""
!!! TARGET PROFILE - FOCUS ON THIS !!!
Name: {profile.get('name') or 'Unknown'}
Location: {profile.get('city') or 'Unknown'}, {profile.get('country') or 'Unknown'}
Phone: {profile.get('phone') or 'Unknown'}
Nickname: {profile.get('nickname') or 'Unknown'}
Additional Clues: {profile.get('other_clues') or 'Unknown'}
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
"""
    ranked_data = sorted(data, key=lambda d: -(d.get("confidence") or 0))
    sources_str = ""
    for i, item in enumerate(ranked_data, start=1):
        reasons = ", ".join(item.get("confidence_reasons") or []) or "no scored signals"
        sources_str += (
            f"\nSOURCE {i} ({item['title']}) [confidence: {item.get('confidence', 0)} - {reasons}]:\n"
            f"{item['url']}\n{item['snippet'][:1000]}\n---\n"
        )

    prompt = f"""You are a STRICT DATA ANALYST.
{target_section}

EVIDENCE COLLECTED (sorted strongest confidence first):
{sources_str}

TASK: Build a confirmed dossier.
HARD RULES:
1. JSON output only.
2. "is_person_found": boolean.
3. "matched_sources": list of dicts {{ "title", "url", "reason" }}.
4. "facts": list of strings.
5. "uncertain": list of strings.
6. "notes": string.
7. A source's TITLE (e.g. "Maigret Found: X", "Match Confidence: High") is a claim,
   not proof. Before listing a source in "matched_sources", read its actual snippet.
   If the snippet is a generic error/template page (not found, doesn't exist, empty
   profile shell, unrelated homepage), it is NOT a match - put the URL in
   "uncertain" instead, and note the contradiction in "notes".
8. A username appearing in a URL is not evidence on its own - the snippet content
   must actually reference the target (name, phone, or other confirmed clue).
9. The bracketed "confidence" number is a pre-computed evidence-strength score, not
   a verdict - a source scored 0-1.5 (e.g. an unverified Maigret claim or a reverse-
   image visual match) needs its own snippet to actually confirm identity before it
   can go in "matched_sources". Never promote a low-confidence source to "matched_sources"
   on the strength of its title or URL alone.

Analyze now."""

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        return {"messages": [response]}
    except Exception as e:
        return {"messages": [SystemMessage(content=f"Error: {e}")]}


async def verify_node(state: AgentState):
    """
    SECOND LLM pass: a skeptical fact-checker that tries to REFUTE every claim in
    the draft dossier against its actual source snippet before anything is allowed
    to stay "confirmed". Directly targets the #1 risk flagged by OSINT-with-AI
    guidance: LLM output must be verified, since hallucinated connections can
    mislead an investigation. Any parse failure here is a no-op - the original
    draft from analyze_node is kept rather than risk destroying it.
    """
    messages = state.get("messages", [])
    if not messages:
        return {}

    draft_raw = messages[-1].content if hasattr(messages[-1], "content") else str(messages[-1])
    draft = _parse_json_loose(draft_raw)
    if not draft:
        print("[VERIFY] Draft dossier wasn't parseable JSON - skipping verification, keeping as-is.")
        return {}

    matched = draft.get("matched_sources", [])
    facts = draft.get("facts", [])
    if not matched and not facts:
        return {}

    data = state.get("gathered_data", [])
    snippet_by_url = {d["url"]: d["snippet"][:1200] for d in data if d.get("url")}

    matched_block = "\n".join(
        f"- CLAIM: {m.get('reason')}\n  URL: {m.get('url')}\n  ACTUAL SNIPPET: "
        f"{snippet_by_url.get(m.get('url'), '[snippet unavailable - treat as unverifiable]')}"
        for m in matched
    ) or "(none)"
    facts_block = "\n".join(f"- {f}" for f in facts) or "(none)"

    llm = ChatCerebras(model="gpt-oss-120b").bind(response_format={"type": "json_object"})
    prompt = f"""You are a SKEPTICAL FACT-CHECKER reviewing another analyst's draft dossier.
Your ONLY job is to try to REFUTE each claim below using the actual snippet text provided.
Default to refuted=true if the snippet does not clearly and specifically support the claim,
or if the snippet is marked unverifiable.

MATCHED SOURCES TO CHECK:
{matched_block}

FREE-TEXT FACTS TO CHECK (no snippet attached - judge plausibility/specificity only):
{facts_block}

Return JSON:
{{
  "matched_sources_verdict": [{{"url": "...", "refuted": bool, "reason": "..."}}],
  "facts_verdict": [{{"fact": "...", "refuted": bool, "reason": "..."}}]
}}"""

    try:
        res = await llm.ainvoke([HumanMessage(content=prompt)])
        verdict = _parse_json_loose(res.content)
    except Exception as e:
        print(f"[VERIFY] Verification pass failed ({e}), keeping draft as-is.")
        return {}

    if not verdict:
        print("[VERIFY] Verifier response wasn't parseable JSON - keeping draft as-is.")
        return {}

    refuted_urls = {v.get("url") for v in verdict.get("matched_sources_verdict", []) if v.get("refuted")}
    refuted_facts = {v.get("fact") for v in verdict.get("facts_verdict", []) if v.get("refuted")}

    kept_matched = [m for m in matched if m.get("url") not in refuted_urls]
    demoted = [m for m in matched if m.get("url") in refuted_urls]
    kept_facts = [f for f in facts if f not in refuted_facts]

    draft["matched_sources"] = kept_matched
    draft["facts"] = kept_facts
    draft.setdefault("uncertain", [])
    draft["uncertain"].extend(d.get("url") for d in demoted if d.get("url"))
    draft["uncertain"].extend(refuted_facts)
    if demoted or refuted_facts:
        draft["notes"] = (draft.get("notes") or "") + (
            f" [Fact-check pass demoted {len(demoted)} source(s) and "
            f"{len(refuted_facts)} fact(s) to uncertain.]"
        )

    print(f"[VERIFY] Kept {len(kept_matched)}/{len(matched)} matched sources, "
          f"{len(kept_facts)}/{len(facts)} facts after fact-check.")

    return {"messages": [SystemMessage(content=json.dumps(draft, ensure_ascii=False))]}


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
workflow.add_node("enrich", enrich_node)
workflow.add_node("extract", extraction_node)
workflow.add_node("analyze", analyze_node)
workflow.add_node("verify", verify_node)

workflow.set_entry_point("validate")

workflow.add_edge("validate", "search")
workflow.add_edge("search", "enrich")
workflow.add_edge("enrich", "extract")

workflow.add_conditional_edges(
    "extract",
    check_loop_condition,
    {
        "loop": "search",
        "finish": "analyze"
    }
)

workflow.add_edge("analyze", "verify")
workflow.add_edge("verify", END)

app = workflow.compile()
