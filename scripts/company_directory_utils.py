"""Shared logic for turning one confirmed company result (whatever produced
it — a live mode:"company" research call, or a row someone saved from the
app's "Save to directory" button) into a data/companies.json entry.

Used by:
  - discover_companies_daily.py  — calls the research backend itself for a
    fixed watchlist of company types/regions.
  - merge_pending_companies.py   — takes rows a person already searched and
    approved in the app (Research Desk or Discover-a-company), so it does
    NOT call the research backend again; the row's own saved fields are
    used as-is.

Kept in one place so both scripts place/dedupe/tag companies identically.
"""
import json
import os
import re
from datetime import date

TODAY = date.today()
REPO_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "companies.json")

CATEGORY_IDS = {
    "automation", "integration", "electrical", "software", "navigation", "cloud",
    "propulsion", "hull", "hvac", "cargo", "safety", "services",
}


def load_directory():
    with open(REPO_DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_directory(directory):
    directory["generated"] = TODAY.isoformat()
    with open(REPO_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(directory, f, indent=2, ensure_ascii=False)


def normalize(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def domain_of(website):
    w = (website or "").strip().lower()
    w = re.sub(r"^https?://", "", w)
    w = re.sub(r"^www\.", "", w)
    return w.split("/")[0]


def existing_signature_set(directory):
    """Every existing company's normalized name and website domain, so we
    never add a duplicate of something already in the directory."""
    sig = set()
    for country in directory["countries"]:
        for region in country["regions"]:
            for co in region["companies"]:
                sig.add(normalize(co.get("name")))
                dom = domain_of(co.get("website"))
                if dom:
                    sig.add(dom)
    return sig


def find_country(directory, country_name):
    target = normalize(country_name)
    for country in directory["countries"]:
        if normalize(country["name"]) == target or normalize(country["id"]) == target:
            return country
    return None


def sibling_local_block(country):
    """Copies the {currency, timezone, language, registrationNumber,
    registryNote} shape from any existing company in this country, instead
    of guessing it for a brand-new one."""
    for region in country["regions"]:
        for co in region["companies"]:
            if co.get("local"):
                return dict(co["local"])
    return None


def find_or_create_region(country, city):
    city = (city or "").strip() or "Unspecified"
    target = normalize(city)
    for region in country["regions"]:
        if normalize(region["name"]) == target or target in normalize(region["name"]):
            return region
    region = {"name": city, "country": country["id"], "companies": []}
    country["regions"].append(region)
    return region


def unique_id(country_id, name, directory):
    base = country_id + "-" + re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", name.lower())).strip("-")
    existing_ids = {co["id"] for c in directory["countries"] for r in c["regions"] for co in r["companies"]}
    candidate = base
    n = 2
    while candidate in existing_ids:
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def build_company_entry(directory, data, source_text):
    """Turns one confirmed company result into a companies.json entry, or
    returns (None, reason) if it can't be placed safely (not found,
    duplicate, or an untracked country).

    `data` shape: {found, name, website, city, country, segment, categories,
    contact: {name, role, email, phone}, sources}.
    `source_text` is a short human-readable note on where this came from,
    used in the entry's `source` field and history — e.g. the watchlist
    query that found it, or "Saved from the app by a user".
    """
    if not data or not data.get("found"):
        return None, "nothing confirmed"

    name = (data.get("name") or "").strip()
    if not name:
        return None, "no name returned"

    sig_existing = existing_signature_set(directory)
    dom = domain_of(data.get("website"))
    if normalize(name) in sig_existing or (dom and dom in sig_existing):
        return None, f"already have {name}"

    country = find_country(directory, data.get("country"))
    if not country:
        return None, f"'{data.get('country')}' isn't a tracked country yet — add it manually if you want {name}"

    local = sibling_local_block(country)
    if not local:
        return None, f"no existing company in {country['name']} to copy currency/timezone from — add {name} manually"

    region = find_or_create_region(country, data.get("city"))
    entry_id = unique_id(country["id"], name, directory)

    cats = [c for c in (data.get("categories") or []) if c in CATEGORY_IDS]

    contacts = []
    c = data.get("contact") or {}
    if c.get("email") or c.get("phone"):
        contact = {"name": c.get("name") or "General Inquiries"}
        if c.get("role"):
            contact["role"] = c["role"]
        if c.get("email"):
            contact["email"] = c["email"]
        if c.get("phone"):
            contact["phone"] = c["phone"]
        contact["source"] = (data.get("sources") or [None])[0] or "AI discovery run"
        contacts.append(contact)

    entry = {
        "id": entry_id,
        "name": name,
        "address": f"{data.get('city')}, {country['name']}" if data.get("city") else country["name"],
        "website": data.get("website") or "",
        "segment": data.get("segment") or "",
        "source": "AI discovery run (single web-search pass) — not yet independently cross-checked, see needsReview",
        "contacts": contacts,
        "stage": "found",
        "lastContact": TODAY.isoformat(),
        "nextAction": "AI drafting first email",
        "needsReview": True,
        "history": [{
            "type": "found",
            "date": TODAY.isoformat(),
            "text": f"Added automatically ({source_text}) — a single AI web-search pass, not yet cross-checked against a second independent source. Worth a quick glance before outreach.",
        }],
        "local": local,
        "instructions": [],
        "categories": cats,
    }
    region["companies"].append(entry)
    return entry, None
