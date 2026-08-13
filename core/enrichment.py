"""
Pivot enrichment for Bakasura.
Scans gathered snippets for emails/IPs/domains, then runs every enrichment source
that's actually free to use:
  - Hunter.io, Shodan, FullContact, HIBP, Social Searcher -> only fire if a key is
    configured (api_services.py already no-ops without one; HIBP/FullContact no
    longer offer a real free tier as of 2026, so in practice those two stay dormant
    unless the user later buys a key - see README note).
  - WHOIS and phone-number lookup -> always free, no API key, run unconditionally.
Never raises: every source is best-effort and failures are swallowed, matching the
"never crashes" contract the rest of api_services.py already follows.
"""
import re
from typing import Dict, List, Set, Tuple

import phonenumbers
from phonenumbers import geocoder, carrier as phone_carrier

from api_services import (
    enrich_hunter_email,
    enrich_hibp,
    enrich_shodan,
    enrich_fullcontact,
)

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

# phonenumbers.PhoneNumberType is plain ints, not a real Python enum - str() on the
# value just gives back the number, so build a name lookup by hand for readability.
_PHONE_TYPE_NAMES = {
    getattr(phonenumbers.PhoneNumberType, n): n
    for n in dir(phonenumbers.PhoneNumberType)
    if not n.startswith("_")
}

# Skip enriching domains behind these - querying "who else uses @gmail.com" is noise,
# not intel about the target.
FREEMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "mail.ru",
    "yandex.ru", "yandex.com", "icloud.com", "protonmail.com", "aol.com",
    "gmx.com", "live.com", "inbox.ru", "bk.ru", "list.ru",
}


def extract_pivots(gathered_data: List[Dict], profile_phone: str = "") -> Dict[str, List[str]]:
    """Regex-scan all snippets for concrete pivots (emails/ips). Dedup'd, order-preserving."""
    emails: List[str] = []
    ips: List[str] = []
    seen_e: Set[str] = set()
    seen_i: Set[str] = set()

    for item in gathered_data:
        text = f"{item.get('title', '')} {item.get('snippet', '')}"
        for m in EMAIL_RE.findall(text):
            m = m.lower()
            if m not in seen_e:
                seen_e.add(m)
                emails.append(m)
        for m in IPV4_RE.findall(text):
            if m not in seen_i and m != profile_phone:
                seen_i.add(m)
                ips.append(m)

    return {"emails": emails, "ips": ips}


def lookup_phone_free(phone: str) -> Dict:
    """
    Offline phone intel via the `phonenumbers` library (Google's libphonenumber port).
    No API key, no network call - pure lookup tables. Gives region/carrier/line-type,
    useful to confirm "this really could be their number" or spot a VOIP/burner number.
    """
    if not phone:
        return {}
    try:
        parsed = phonenumbers.parse(phone, None)
        if not phonenumbers.is_valid_number(parsed):
            return {}
        return {
            "valid": True,
            "region": geocoder.description_for_number(parsed, "en") or "",
            "carrier": phone_carrier.name_for_number(parsed, "en") or "",
            "number_type": _PHONE_TYPE_NAMES.get(phonenumbers.number_type(parsed), "UNKNOWN"),
            "e164": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164),
        }
    except Exception as e:
        print(f"[PHONE LOOKUP] Failed for {phone}: {e}")
        return {}


def lookup_whois_free(domain: str) -> Dict:
    """WHOIS lookup via python-whois - free, no key, direct WHOIS protocol query."""
    try:
        import whois as whois_lib
        w = whois_lib.whois(domain)
        if not w or not w.domain_name:
            return {}
        return {
            "domain": domain,
            "registrar": w.registrar or "",
            "creation_date": str(w.creation_date) if w.creation_date else "",
            "org": getattr(w, "org", "") or "",
            "emails": w.emails if isinstance(w.emails, list) else ([w.emails] if w.emails else []),
            "name": getattr(w, "name", "") or "",
        }
    except Exception as e:
        print(f"[WHOIS] Failed for {domain}: {e}")
        return {}


def enrich_pivots(gathered_data: List[Dict], profile: Dict,
                   processed: Dict[str, List[str]]) -> Tuple[List[Dict], Dict[str, List[str]]]:
    """
    Runs every enrichment source over NEW pivots only (skips anything already in
    `processed`, so re-running doesn't repeat the same lookups every loop).
    Returns (new_source_items, updated_processed).
    """
    pivots = extract_pivots(gathered_data, profile.get("phone", ""))
    processed = {k: list(v) for k, v in (processed or {"emails": [], "ips": [], "domains": []}).items()}
    processed.setdefault("domains", [])
    new_items: List[Dict] = []

    new_emails = [e for e in pivots["emails"] if e not in processed["emails"]]
    new_ips = [i for i in pivots["ips"] if i not in processed["ips"]]

    for email in new_emails:
        processed["emails"].append(email)
        domain = email.split("@", 1)[1] if "@" in email else ""

        for breach in enrich_hibp(email):
            new_items.append({
                "title": f"HIBP Breach: {breach.get('name', 'Unknown')}",
                "url": "https://haveibeenpwned.com/",
                "snippet": f"Email {email} found in breach '{breach.get('name')}' "
                           f"({breach.get('date')}). Exposed: {breach.get('data_classes')}",
            })

        fc = enrich_fullcontact(email)
        if fc:
            new_items.append({
                "title": f"FullContact Profile: {fc.get('name') or email}",
                "url": "https://fullcontact.com/",
                "snippet": f"Location: {fc.get('location')}. Bio: {fc.get('bio')}. "
                           f"Social: {fc.get('social_profiles')}",
            })

        if domain and domain not in FREEMAIL_DOMAINS and domain not in processed["domains"]:
            processed["domains"].append(domain)
            for hit in enrich_hunter_email(domain):
                new_items.append({
                    "title": f"Hunter.io: {hit.get('email', domain)}",
                    "url": f"https://hunter.io/",
                    "snippet": f"Email pattern for domain {domain}: {hit.get('email')} "
                               f"(confidence {hit.get('confidence')}, type {hit.get('type')})",
                })
            whois_data = lookup_whois_free(domain)
            if whois_data:
                new_items.append({
                    "title": f"WHOIS: {domain}",
                    "url": f"https://who.is/whois/{domain}",
                    "snippet": f"Registrar: {whois_data.get('registrar')}. "
                               f"Created: {whois_data.get('creation_date')}. "
                               f"Org/Name: {whois_data.get('org') or whois_data.get('name')}. "
                               f"WHOIS emails: {whois_data.get('emails')}",
                })

    for ip in new_ips:
        processed["ips"].append(ip)
        shodan_data = enrich_shodan(ip)
        if shodan_data:
            new_items.append({
                "title": f"Shodan: {ip}",
                "url": f"https://www.shodan.io/host/{ip}",
                "snippet": f"Org: {shodan_data.get('org')}. Country: {shodan_data.get('country')}. "
                           f"Hostnames: {shodan_data.get('hostnames')}. Open ports: {shodan_data.get('ports')}",
            })

    return new_items, processed
