#!/usr/bin/env python3
"""Daily automated company-DIRECTORY growth run (as opposed to the project
signals in ai_research_daily.py, which this file deliberately mirrors).

Until this script existed, the company directory (data/companies.json) only
grew when a person manually researched and added a company during a chat —
it never discovered new prospects on its own the way the daily project
research already does. This closes that gap: it asks the SAME backend
(supabase/functions/research, called here with mode: "company") about a
FIXED, bounded watchlist of company TYPES and regions, and appends any real,
verifiable, genuinely-new company it finds to data/companies.json.

Same cost-control philosophy as ai_research_daily.py: a fixed watchlist
caps this at a small, predictable number of Anthropic calls per day,
completely separate from ad-hoc "Search live" usage.

Important honesty note: a single AI web-search pass is NOT the same bar as
the two-independent-source manual verification the rest of this directory
was built with (see data/companies.json's own "note" field). Every entry
this script adds is therefore tagged needsReview: true and given a history
entry that says so plainly — a person should give it a quick glance (its
own website is usually enough) before relying on it for outreach.

New companies are only placed under a country that ALREADY exists in
data/companies.json (so currency/timezone/language metadata is real,
copied from a sibling company in that country, never guessed). A result in
a country the directory doesn't have yet is logged and skipped rather than
inventing that metadata — a person can add that country manually, the same
way every country in this file started.
"""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import date

TODAY = date.today()
REPO_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "companies.json")

REQUEST_DELAY_SECONDS = 3

# Fixed, bounded watchlist — company TYPE + region. Weighted toward the UAE
# gaps flagged directly (automation integrators, vessel owners/operators),
# plus a handful of the same company types in other countries the directory
# already tracks, so this starts generalizing beyond just the UAE.
WATCHLIST = [
    "marine automation and navigation systems integrator company headquartered in Dubai or Abu Dhabi, UAE",
    "vessel owner or ship operator company headquartered in Dubai or Abu Dhabi, UAE, operating a fleet of commercial vessels",
    "marine engine control unit, thruster control, or automation retrofit company in the UAE",
    "shore power converter or marine electrical systems company in the UAE",
    "unmanned surface vessel (USV) or autonomous marine systems developer company in the UAE",
    "ship management company headquartered in Dubai, UAE",
    "marine navigation, radar, or communication equipment supplier company in Abu Dhabi or Sharjah, UAE",
    "vessel owner or tanker/bulk carrier operator company headquartered in Singapore",
    "marine automation or navigation systems integrator company in Norway",
    "ship owner or offshore vessel operator company headquartered in Qatar",
    "marine systems integrator or automation company in Saudi Arabia",
    "vessel owner, ferry operator, or offshore support vessel operator company in Greece",
]

CATEGORY_IDS = {
    "automation", "integration", "electrical", "software", "navigation", "cloud",
    "propulsion", "hull", "hvac", "cargo", "safety", "services",
}


def call_research_backend(query, research_url, anon_key, mode):
    payload = json.dumps({"query": query, "mode": mode}).encode("utf-8")
    req = urllib.request.Request(
        research_url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "apikey": anon_key,
            "Authorization": "Bearer " + anon_key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"  ! HTTP {e.code} for query {query!r}: {e.read().decode('utf-8', 'ignore')[:300]}")
        return None
    except Exception as e:
        print(f"  ! error for query {query!r}: {e}")
        return None


def load_directory():
    with open(REPO_DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


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


def build_company_entry(directory, data, query):
    """Turns one confirmed mode:'company' research result into a
    companies.json entry, or returns (None, reason) if it can't be placed
    safely (not found, duplicate, or an untracked country)."""
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
            "text": "Added automatically by the daily company-discovery run (query: \"" + query + "\") — a single AI web-search pass, not yet cross-checked against a second independent source. Worth a quick glance before outreach.",
        }],
        "local": local,
        "instructions": [],
        "categories": cats,
    }
    region["companies"].append(entry)
    return entry, None


def main():
    research_url = os.environ.get("RESEARCH_URL", "").strip()
    anon_key = os.environ.get("RESEARCH_ANON_KEY", "").strip()
    if not research_url or not anon_key:
        print("RESEARCH_URL / RESEARCH_ANON_KEY not set — skipping automatic company-discovery run.")
        return 0

    directory = load_directory()
    added = []

    for i, query in enumerate(WATCHLIST):
        print(f"[{i+1}/{len(WATCHLIST)}] {query}")
        data = call_research_backend(query, research_url, anon_key, mode="company")
        time.sleep(REQUEST_DELAY_SECONDS)

        entry, reason = build_company_entry(directory, data, query)
        if not entry:
            print(f"  - {reason}")
            continue
        added.append(entry)
        print(f"  + added: {entry['name']} ({entry['address']})")

    if not added:
        print("\nNo new companies found today — data/companies.json unchanged.")
        return 0

    directory["generated"] = TODAY.isoformat()
    with open(REPO_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(directory, f, indent=2, ensure_ascii=False)

    print(f"\nAdded {len(added)} new compan{'y' if len(added)==1 else 'ies'}, flagged needsReview for a quick glance. Written to {REPO_DATA_PATH}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
