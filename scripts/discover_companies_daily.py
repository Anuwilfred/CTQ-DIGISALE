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

Placement/dedup/needsReview logic lives in company_directory_utils.py,
shared with merge_pending_companies.py (which handles companies a person
searched and chose to save from inside the app itself, rather than this
fixed watchlist).
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

from company_directory_utils import build_company_entry, load_directory, save_directory

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

        entry, reason = build_company_entry(directory, data, f'daily watchlist query: "{query}"')
        if not entry:
            print(f"  - {reason}")
            continue
        added.append(entry)
        print(f"  + added: {entry['name']} ({entry['address']})")

    if not added:
        print("\nNo new companies found today — data/companies.json unchanged.")
        return 0

    save_directory(directory)
    print(f"\nAdded {len(added)} new compan{'y' if len(added)==1 else 'ies'}, flagged needsReview for a quick glance. Written to data/companies.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
