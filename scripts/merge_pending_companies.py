#!/usr/bin/env python3
"""Folds companies saved from inside the app (Research Desk's or
Discover-a-company's "Save to directory" button) into the real
data/companies.json.

The app itself is a static site with no server of its own, so "Save to
directory" cannot write to companies.json directly — it POSTs the company
into a small Supabase table (pending_companies) instead. This script is the
other half: it runs daily, reads whatever is waiting in that table, places
each one using the exact same rules as the automatic watchlist discovery
(company_directory_utils.build_company_entry — only a country already
tracked in the directory, real currency/timezone copied from a sibling
company, no duplicates), and removes each row it successfully placed (or
that turned out to already be a duplicate) so it isn't processed again.

Deliberately does NOT call the research backend again — the row already
holds exactly what the person saw and chose to save in the app, so
re-querying could silently change the facts.

A row that can't be placed yet (its country isn't tracked, most likely) is
left in the table rather than dropped, so it stays visible — via a
`select id,name,country&country not in tracked` glance, or just the table
itself — for someone to resolve by adding that country manually.
"""
import json
import os
import sys
import urllib.request
import urllib.error

from company_directory_utils import build_company_entry, load_directory, save_directory


def supabase_base_url(research_url):
    import re
    m = re.match(r"^(https://[^/]+\.supabase\.co)/", research_url or "")
    return m.group(1) if m else None


def rest_request(method, url, anon_key, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "apikey": anon_key,
            "Authorization": "Bearer " + anon_key,
            "Prefer": "return=representation",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else None


def fetch_pending(base, anon_key):
    url = f"{base}/rest/v1/pending_companies?select=id,name,website,city,country,segment,categories,contact,sources,created_at&order=created_at.asc"
    try:
        return rest_request("GET", url, anon_key) or []
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print("pending_companies table doesn't exist yet — nothing to merge (see SETUP.md's \"Save a discovered company\" section).")
            return []
        print(f"! could not fetch pending_companies: HTTP {e.code} {e.read().decode('utf-8', 'ignore')[:300]}")
        return []
    except Exception as e:
        print(f"! could not fetch pending_companies: {e}")
        return []


def delete_pending(base, anon_key, row_id):
    url = f"{base}/rest/v1/pending_companies?id=eq.{row_id}"
    try:
        rest_request("DELETE", url, anon_key)
    except Exception as e:
        print(f"  ! could not remove processed row {row_id}: {e}")


def main():
    research_url = os.environ.get("RESEARCH_URL", "").strip()
    anon_key = os.environ.get("RESEARCH_ANON_KEY", "").strip()
    if not research_url or not anon_key:
        print("RESEARCH_URL / RESEARCH_ANON_KEY not set — skipping pending-companies merge.")
        return 0

    base = supabase_base_url(research_url)
    if not base:
        print("RESEARCH_URL doesn't look like a Supabase functions URL — skipping.")
        return 0

    rows = fetch_pending(base, anon_key)
    if not rows:
        print("No companies saved from the app waiting to merge.")
        return 0

    directory = load_directory()
    added = []
    to_delete = []

    for row in rows:
        data = {
            "found": True,
            "name": row.get("name"),
            "website": row.get("website"),
            "city": row.get("city"),
            "country": row.get("country"),
            "segment": row.get("segment"),
            "categories": row.get("categories") or [],
            "contact": row.get("contact") or {},
            "sources": row.get("sources") or [],
        }
        entry, reason = build_company_entry(directory, data, "saved from the app")
        if entry:
            added.append(entry)
            to_delete.append(row["id"])
            print(f"+ merged: {entry['name']} ({entry['address']})")
        elif reason and reason.startswith("already have"):
            # Already in the directory some other way — nothing to merge,
            # but no reason to keep this row around either.
            to_delete.append(row["id"])
            print(f"- skipped (duplicate), removing from queue: {row.get('name')}")
        else:
            print(f"- left in queue ({reason}): {row.get('name')}")

    if added:
        save_directory(directory)
        print(f"\nMerged {len(added)} compan{'y' if len(added)==1 else 'ies'} into data/companies.json.")
    else:
        print("\nNothing new to merge — data/companies.json unchanged.")

    for row_id in to_delete:
        delete_pending(base, anon_key, row_id)

    return 0


if __name__ == "__main__":
    sys.exit(main())
