#!/usr/bin/env python3
"""Folds job-category tags saved from inside the app's Services tab into the
real data/companies.json.

Tapping a job-category tile's "+ Add" button in the app POSTs the company's
full category list into a small Supabase table (category_overrides), keyed
by company id, and the app reads that table back on every load so the tags
show up immediately for everyone. That's enough on its own to make tagging
durable, but the table is meant to be a thin, temporary layer on top of the
real directory rather than a second permanent home for the data — this
script is the other half: it runs daily, copies each override's categories
onto the matching company in companies.json, and removes the row once it's
been applied so the table only ever holds whatever has been tagged since the
last run.

A row whose company id isn't found in companies.json (the company was
removed, or the id changed) is left in place rather than dropped, so it
stays visible for someone to check rather than silently disappearing.
"""
import json
import os
import sys
import urllib.request
import urllib.error
import urllib.parse

from company_directory_utils import load_directory, save_directory


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


def fetch_overrides(base, anon_key):
    url = f"{base}/rest/v1/category_overrides?select=company_id,categories,updated_at&order=updated_at.asc"
    try:
        return rest_request("GET", url, anon_key) or []
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print("category_overrides table doesn't exist yet — nothing to apply (see SETUP.md's \"Job-category tags\" section).")
            return []
        print(f"! could not fetch category_overrides: HTTP {e.code} {e.read().decode('utf-8', 'ignore')[:300]}")
        return []
    except Exception as e:
        print(f"! could not fetch category_overrides: {e}")
        return []


def delete_override(base, anon_key, company_id):
    url = f"{base}/rest/v1/category_overrides?company_id=eq.{urllib.parse.quote(company_id)}"
    try:
        rest_request("DELETE", url, anon_key)
    except Exception as e:
        print(f"  ! could not remove applied row {company_id}: {e}")


def find_company(directory, company_id):
    for country in directory.get("countries", []):
        for region in country.get("regions", []):
            for company in region.get("companies", []):
                if company.get("id") == company_id:
                    return company
    return None


def main():
    research_url = os.environ.get("RESEARCH_URL", "").strip()
    anon_key = os.environ.get("RESEARCH_ANON_KEY", "").strip()
    if not research_url or not anon_key:
        print("RESEARCH_URL / RESEARCH_ANON_KEY not set — skipping category-override merge.")
        return 0

    base = supabase_base_url(research_url)
    if not base:
        print("RESEARCH_URL doesn't look like a Supabase functions URL — skipping.")
        return 0

    rows = fetch_overrides(base, anon_key)
    if not rows:
        print("No category tags waiting to apply.")
        return 0

    directory = load_directory()
    applied = []
    to_delete = []

    for row in rows:
        company_id = row.get("company_id")
        categories = row.get("categories") or []
        company = find_company(directory, company_id)
        if company is None:
            print(f"- left in queue (no matching company id): {company_id}")
            continue
        company["categories"] = categories
        applied.append(company_id)
        to_delete.append(company_id)
        print(f"+ applied: {company.get('name')} -> {categories}")

    if applied:
        save_directory(directory)
        print(f"\nApplied {len(applied)} category tag change{'s' if len(applied) != 1 else ''} to data/companies.json.")
    else:
        print("\nNothing new to apply — data/companies.json unchanged.")

    for company_id in to_delete:
        delete_override(base, anon_key, company_id)

    return 0


if __name__ == "__main__":
    sys.exit(main())
