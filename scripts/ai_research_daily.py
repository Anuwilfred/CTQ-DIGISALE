#!/usr/bin/env python3
"""Daily automated AI research run for C-TORQ's Active Projects data.

This is the "AI searches on its own" half of the app: instead of a person
clicking "Search live" in the Research desk, this script runs once a day
(from a GitHub Actions cron, see .github/workflows/ai-research-daily.yml)
and asks the SAME backend (the Supabase Edge Function in
supabase/functions/research/) about a FIXED, bounded watchlist of real
shipyards, systems suppliers and discovery queries relevant to C-TORQ's
business (automation, navigation, AMS, LNG, fire & gas safety).

Why a fixed watchlist instead of unlimited/open-ended search: it caps the
number of Anthropic API calls per day to a known, predictable number
regardless of how many people are using the app that day — the automatic
side of the system never scales with user traffic, so cost and API rate
stay flat and predictable. (The manual "Search live" box in the app is
separate and additional, and is on the person clicking it.)

New, genuinely-actionable findings (real project/company, systems supplier
still open) are merged into data/active_projects.json, re-scored with the
same priority formula the rest of the app uses, deduplicated against what
is already there, and written back out. Nothing is ever invented — if the
AI can't confirm something with a real source, it's skipped.
"""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import date, datetime

TODAY = date.today()
REPO_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "active_projects.json")

# Same weights as build_active_projects.py / index.html's priority logic —
# keep these three in sync if the category list ever changes.
CATEGORY_WEIGHT = {
    "automation": 10, "navigation": 9, "safety": 8, "integration": 7,
    "electrical": 6, "software": 6, "cloud": 5, "propulsion": 4,
    "cargo": 3, "hull": 2, "hvac": 2, "services": 2,
}

# Fixed, bounded watchlist — this is the entire "AI rate" for the day.
# A mix of (a) real companies already in our directory that are active in
# C-TORQ's specialty, checked for fresh news, and (b) a few open discovery
# queries to catch new projects not yet in our directory at all.
WATCHLIST = [
    "Kongsberg Maritime new vessel automation or navigation contract announced this month",
    "Vard Group new vessel contract systems supplier automation navigation",
    "Ulstein Group new vessel contract automation navigation system",
    "HAV Group new vessel electrification automation contract",
    "Damen Shipyards new vessel contract automation navigation systems supplier",
    "Fincantieri new naval or cruise vessel contract fire safety systems",
    "TKMS thyssenkrupp Marine Systems new submarine or frigate contract",
    "Meyer Werft new cruise ship contract automation systems",
    "HD Hyundai Heavy Industries new LNG carrier or naval vessel contract automation",
    "Hanwha Ocean new LNG carrier or naval vessel contract systems supplier",
    "Samsung Heavy Industries new vessel order automation navigation systems",
    "Cochin Shipyard new vessel contract navigation automation systems",
    "Mazagon Dock Shipbuilders new naval vessel contract systems supplier",
    "Garden Reach Shipbuilders new naval vessel contract automation systems",
    "Austal new vessel contract navigation automation systems supplier",
    "Praxis Automation new integrated platform management system contract",
    "Consilium Safety Group new fire and gas detection system contract shipyard",
    "new LNG carrier contract signed this year automation navigation system not yet awarded",
    "new offshore support vessel contract dynamic positioning system supplier not yet named",
    "new naval frigate or corvette contract fire and gas safety system supplier",

    # Classification-agreement signals — DNV, ABS, Lloyd's Register, Bureau
    # Veritas, ClassNK and RINA get engaged right at project kickoff, often
    # before a shipyard's own contract-signing press release, so this is
    # frequently the EARLIEST public sign a project exists at all. Global —
    # not restricted to any one country/region.
    "new vessel classification agreement signed this month DNV or ABS or Lloyd's Register systems not yet awarded",
    "shipyard newbuilding series assigned class this year automation navigation system supplier not yet named",
    "DNV approval in principle new vessel design this year systems supplier",
    "classification society new offshore support vessel class agreement automation navigation system",
    "new LNG carrier classed by class society this year systems integrator not yet awarded",
    "UAE shipyard new vessel classification agreement this year automation navigation systems",
    "new naval vessel classification agreement fire and gas safety system supplier not yet named",
    "new hybrid or battery electric vessel classification agreement battery notation systems supplier",
]

REQUEST_DELAY_SECONDS = 3  # be polite / stay well under any rate limit


def call_research_backend(query, research_url, anon_key):
    payload = json.dumps({"query": query}).encode("utf-8")
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


def recency_score(d):
    days = (TODAY - d).days
    if days <= 30: return 10
    if days <= 90: return 8
    if days <= 180: return 6
    if days <= 365: return 4
    return 2


def priority(cats, d):
    cat_score = max((CATEGORY_WEIGHT.get(c, 1) for c in cats), default=1)
    return round(cat_score * 1.4 + recency_score(d), 1)


def normalize_key(title, companies):
    base = (title or "") + "|" + "|".join(sorted(companies or []))
    return re.sub(r"[^a-z0-9]+", "", base.lower())


def load_existing():
    try:
        with open(REPO_DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def next_id(existing):
    nums = []
    for item in existing:
        m = re.match(r"proj-(\d+)$", item.get("id", ""))
        if m:
            nums.append(int(m.group(1)))
        m2 = re.match(r"ai-proj-(\d+)$", item.get("id", ""))
        if m2:
            nums.append(int(m2.group(1)))
    return (max(nums) + 1) if nums else 1


def build_entry(n, query, data, source_name):
    """Turn one confirmed research-backend result into an active_projects.json
    entry, or return None if it's not actionable (nothing found, or a
    competitor's systems are already publicly awarded there)."""
    if not data or not data.get("found"):
        return None
    if data.get("systemsStatus") == "already_awarded":
        print(f"  - real, but systems already awarded to {data.get('systemsAwardedTo')} — skipping (not actionable)")
        return None

    title = data.get("name") or query
    companies = data.get("companies") or []
    cats = data.get("categories") or []
    d = TODAY  # AI research doesn't give us a precise contract date; date it as of discovery
    return {
        "id": "ai-proj-%03d" % n,
        "title": title,
        "companies": companies,
        "vesselType": data.get("vesselType") or "",
        "summary": data.get("summary") or "",
        "date": d.isoformat(),
        "categories": cats,
        "sourceUrl": (data.get("sources") or [None])[0] or "",
        "sourceName": source_name,
        "priority": priority(cats, d),
        "systemsStatus": data.get("systemsStatus") or "unknown",
        "systemsAwardedTo": data.get("systemsAwardedTo"),
    }


def supabase_base_url(research_url):
    """research_url looks like https://xxxx.supabase.co/functions/v1/research
    — this derives the project's own base URL for hitting its REST API
    (PostgREST) directly, the same way index.html's supabaseBaseUrl() does."""
    m = re.match(r"^(https://[^/]+\.supabase\.co)/", research_url)
    return m.group(1) if m else ""


def fetch_watched_sources(research_url, anon_key):
    """Reads the 'Watched websites' a person added from the app's Settings
    tab (stored in the watched_sources Supabase table — see SETUP.md). Added
    with zero code push; if the table doesn't exist yet (not set up), this
    just returns an empty list so the rest of the run proceeds normally."""
    base = supabase_base_url(research_url)
    if not base:
        return []
    url = base + "/rest/v1/watched_sources?select=url,label"
    req = urllib.request.Request(url, headers={"apikey": anon_key, "Authorization": "Bearer " + anon_key})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print("(No 'watched_sources' table yet — skipping watched-website checks. "
                  "See SETUP.md's \"Watched websites\" section if you want this.)")
        else:
            print(f"  ! could not fetch watched sources: HTTP {e.code}")
        return []
    except Exception as e:
        print(f"  ! could not fetch watched sources: {e}")
        return []


def main():
    research_url = os.environ.get("RESEARCH_URL", "").strip()
    anon_key = os.environ.get("RESEARCH_ANON_KEY", "").strip()
    if not research_url or not anon_key:
        print("RESEARCH_URL / RESEARCH_ANON_KEY not set — skipping automatic AI research run "
              "(the Research desk in the app itself isn't wired up yet either; see SETUP.md).")
        return 0

    existing = load_existing()
    existing_keys = {normalize_key(item.get("title"), item.get("companies")) for item in existing}

    added = []
    n = next_id(existing)

    for i, query in enumerate(WATCHLIST):
        print(f"[{i+1}/{len(WATCHLIST)}] {query}")
        data = call_research_backend(query, research_url, anon_key)
        time.sleep(REQUEST_DELAY_SECONDS)

        entry = build_entry(n, query, data, "AI research (web search)")
        if not entry:
            print("  - nothing confirmed")
            continue
        key = normalize_key(entry["title"], entry["companies"])
        if key in existing_keys:
            print("  - already have this one")
            continue
        n += 1
        existing_keys.add(key)
        added.append(entry)
        print(f"  + added: {entry['title']}")

    # Watched websites — a person can add any company's site from the app's
    # Settings tab (no code push needed); this checks each one for real news
    # the same way the fixed watchlist above does, so nobody has to notice a
    # press release themselves and type it in.
    watched = fetch_watched_sources(research_url, anon_key)
    if watched:
        print(f"\nChecking {len(watched)} watched website(s)...")
    for i, src in enumerate(watched):
        label = src.get("label") or src.get("url")
        query = (
            f"Recent news, press release, or new vessel/contract announcement from {label} "
            f"({src.get('url')}) — a shipyard, marine systems supplier, or maritime technology company — "
            f"in the past few weeks"
        )
        print(f"[watched {i+1}/{len(watched)}] {label}")
        data = call_research_backend(query, research_url, anon_key)
        time.sleep(REQUEST_DELAY_SECONDS)

        entry = build_entry(n, query, data, f"Watched website: {label}")
        if not entry:
            print("  - nothing confirmed")
            continue
        key = normalize_key(entry["title"], entry["companies"])
        if key in existing_keys:
            print("  - already have this one")
            continue
        n += 1
        existing_keys.add(key)
        added.append(entry)
        print(f"  + added: {entry['title']}")

    if not added:
        print("\nNo new actionable projects found today — data/active_projects.json unchanged.")
        return 0

    merged = existing + added
    merged.sort(key=lambda x: x.get("priority", 0), reverse=True)

    with open(REPO_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)

    print(f"\nAdded {len(added)} new project(s). Total now {len(merged)}. Written to {REPO_DATA_PATH}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
