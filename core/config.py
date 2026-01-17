"""
API Key Management for Bakasura
Keys are stored in a local JSON file and loaded on demand.
"""
import json
import os
from typing import Optional, Dict

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "api_keys.json")

# Ensure config directory exists
os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)

def load_keys() -> Dict[str, str]:
    """Load all API keys from config file."""
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[CONFIG] Failed to load keys: {e}")
        return {}

def save_keys(keys: Dict[str, str]) -> bool:
    """Save API keys to config file."""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(keys, f, indent=2)
        return True
    except Exception as e:
        print(f"[CONFIG] Failed to save keys: {e}")
        return False

def get_key(service: str) -> Optional[str]:
    """Get a specific API key. Returns None if not set or empty."""
    keys = load_keys()
    key = keys.get(service, "")
    return key if key else None

def set_key(service: str, value: str) -> bool:
    """Set a specific API key."""
    keys = load_keys()
    keys[service] = value
    return save_keys(keys)

# Service names (for reference)
SERVICES = [
    "brave_search",      # Brave Search API
    "exa_ai",            # Exa.ai semantic search
    "hunter_io",         # Hunter.io email finder
    "hibp",              # Have I Been Pwned
    "shodan",            # Shodan IoT search
    "fullcontact",       # FullContact person enrichment
    "clearbit",          # Clearbit company data
    "social_searcher",   # Social Searcher
]
