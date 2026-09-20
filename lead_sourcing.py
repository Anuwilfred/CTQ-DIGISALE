#!/usr/bin/env python3
"""
C-TORQ lead sourcing pipeline
=============================

Turns the "Compliant lead sourcing" section of the architecture doc into
runnable code. It only touches public, compliant sources -- no LinkedIn
scraping, no personal-data harvesting.

WHERE TO RUN THIS
------------------
Run it on your own machine, or as a scheduled GitHub Actions job (the free
tier the architecture doc already recommends for automation). It needs
normal outbound internet access to opencorporates.com and the maritime
press sites below -- it will NOT work from a locked-down sandbox/CI
runner that blocks arbitrary outbound domains.

SOURCES, AND WHAT EACH ONE ACTUALLY NEEDS TODAY (checked Sept 2026)
---------------------------------------------------------------------
1. OpenCorporates company search
   - `api.opencorporates.com` now returns 401 Unauthorized on search
     without an api_token -- OpenCorporates tightened free access.
     Free tokens are granted case-by-case to public-interest projects
     (apply at https://opencorporates.com/api_accounts/new); otherwise
     it's a paid plan. Put your token in OPENCORPORATES_API_TOKEN or
     pass --token. Until you have one, this function will raise a clear
     error rather than silently returning nothing.

2. Maritime trade press / newbuilding-contract trackers
   - No signup needed. This is the most reliable free signal source
     right now for "new vessel agreement signed" events -- e.g.
     new-ships.com publishes a weekly newbuilding-contracts roundup.
   - `scrape_newbuild_contracts()` below is a generic, defensive parser:
     it looks for paragraph/list text containing an "X ordered N vessels
     at Y shipyard" pattern. Maritime news sites change their HTML often,
     so treat the CSS selectors as a starting point to adjust once you
     point this at a live page from your own network.

3. RSS/Atom feeds from maritime trade press
   - No signup needed. `monitor_rss_feeds()` pulls entries and keyword-
     filters for newbuild/contract/order/classification language. Add
     feed URLs for the outlets you follow (Splash247, Marine Log,
     gCaptain, Offshore Energy, TradeWinds's free RSS, Seatrade Maritime
     News, etc. -- confirm each outlet's current feed URL and terms
     before relying on it).
   - Classification societies (DNV, ABS, Lloyd's Register, Bureau
     Veritas, ClassNK, RINA) generally don't publish their own public
     RSS feeds -- they push news via email subscriptions instead. So
     rather than watching a class society's own site, NEWBUILD_KEYWORDS
     below includes classification-agreement language (e.g. "to class",
     "classification agreement", "class notation") so a class-order
     announcement covered by the maritime trade press outlets already
     being monitored still gets caught. This is deliberately an early
     signal: class gets assigned right at project kickoff, often before
     a shipyard's own contract-signing press release.

4. Equasis (vessel/owner data) and IMO GISIS (company/vessel registry)
   - Both require you to hold a free registered account and use their
     web search UI; neither publishes an open bulk API today. This
     script does not scrape them -- automating around a login wall
     would violate their terms. Look up specific vessels/owners by hand,
     or export what their UI allows, then feed the results through
     `normalize_lead()` below to get them into the same shape as
     everything else.

A NOTE ON LINKEDIN
-------------------
LinkedIn's terms of service prohibit automated scraping / bulk data
collection, so nothing in this pipeline touches it. If you want LinkedIn
company or contact data specifically, do that lookup yourself in the
LinkedIn UI (or Sales Navigator) and paste the results in -- they'll
still flow through `normalize_lead()` into the same shape as everything
else here.

OUTPUT SHAPE
------------
Every source function returns a list of dicts normalized by
`normalize_lead()`. `build_dashboard_tree()` then nests those into the
same {country -> region -> company} tree the C-TORQ Sales Command
dashboard's sample DATA array uses, so the JSON this script writes can
be dropped straight into that page (or, once Supabase is wired up,
upserted into the `companies` table from the architecture doc's schema).

Every lead starts at stage "found" with a single history entry recording
*why* it was found and citing the source. Nothing fabricates a reply, a
meeting, or a signed deal -- those only get added once they genuinely
happen, via the approval-gated email workflow described in the doc.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

try:
    import feedparser
except ImportError:  # pragma: no cover
    feedparser = None

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None


REQUEST_TIMEOUT = 20
USER_AGENT = "CTORQ-LeadSourcing/1.0 (+compliant company-level research; contact: sales@c-torq.example)"


def _require(pkg, name):
    if pkg is None:
        raise SystemExit(
            f"Missing dependency '{name}'. Install with: pip install {name} --break-system-packages"
        )


# --------------------------------------------------------------------------
# Normalization -- every source funnels through this so the dashboard,
# and eventually Supabase, only ever sees one shape.
# --------------------------------------------------------------------------

@dataclass
class Lead:
    name: str
    country_code: str          # ISO-ish short code used by the dashboard: 'no','kr','ae','sg','cn',...
    country_name: str
    region: str
    segment: str = ""
    address: str | None = None
    website: str | None = None
    source: str = ""
    source_url: str | None = None
    found_reason: str = "Discovered via compliant public-source lookup."
    contacts: list[dict] = field(default_factory=list)   # left empty unless you have a compliant, public contact
    found_date: str = field(default_factory=lambda: date.today().isoformat())

    def slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", f"{self.country_code}-{self.name}".lower()).strip("-")

    def to_dashboard_company(self) -> dict:
        return {
            "id": self.slug(),
            "name": self.name,
            "address": self.address or "Address not yet compliantly sourced",
            "website": self.website or "",
            "segment": self.segment or "Uncategorised — needs review",
            "source": self.source,
            "sourceUrl": self.source_url,
            "contacts": self.contacts,
            "stage": "found",
            "lastContact": self.found_date,
            "nextAction": "Enrich with a compliant public contact, then let the AI draft the first outreach email.",
            "history": [
                {"type": "found", "date": self.found_date, "text": self.found_reason}
            ],
        }


def normalize_lead(
    name: str,
    country_code: str,
    country_name: str,
    region: str,
    **kwargs: Any,
) -> Lead:
    return Lead(name=name, country_code=country_code, country_name=country_name, region=region, **kwargs)


def build_dashboard_tree(leads: list[Lead]) -> list[dict]:
    """Nest leads into the {country -> region -> company[]} shape the
    dashboard's sample DATA array uses, so this can be pasted straight in."""
    countries: dict[str, dict] = {}
    for lead in leads:
        c = countries.setdefault(
            lead.country_code, {"id": lead.country_code, "name": lead.country_name, "regions": {}}
        )
        r = c["regions"].setdefault(lead.region, {"name": lead.region, "country": lead.country_code, "companies": []})
        r["companies"].append(lead.to_dashboard_company())
    out = []
    for c in countries.values():
        out.append({"id": c["id"], "name": c["name"], "regions": list(c["regions"].values())})
    return out


# --------------------------------------------------------------------------
# 1. OpenCorporates company search
# --------------------------------------------------------------------------

def search_opencorporates(
    keyword: str,
    jurisdiction_code: str,
    api_token: str | None = None,
    per_page: int = 30,
) -> list[dict]:
    """Search OpenCorporates for companies matching `keyword` in a
    jurisdiction (e.g. 'no' for Norway, 'kr' for South Korea).

    Raises a RuntimeError with guidance if OpenCorporates rejects the
    request for lacking a token -- as of Sept 2026 that's the normal
    outcome without one, not a bug in this script.
    """
    _require(requests, "requests")
    api_token = api_token or os.environ.get("OPENCORPORATES_API_TOKEN")
    params = {"q": keyword, "jurisdiction_code": jurisdiction_code, "per_page": per_page}
    if api_token:
        params["api_token"] = api_token

    resp = requests.get(
        "https://api.opencorporates.com/v0.4/companies/search",
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code == 401:
        raise RuntimeError(
            "OpenCorporates returned 401 Unauthorized. Free search access is now "
            "granted on application (apply at "
            "https://opencorporates.com/api_accounts/new) or via a paid plan. "
            "Set OPENCORPORATES_API_TOKEN once you have one."
        )
    resp.raise_for_status()
    payload = resp.json()
    companies = payload.get("results", {}).get("companies", [])
    return [c["company"] for c in companies]


def opencorporates_to_leads(raw_companies: list[dict], country_name: str, default_region: str, segment: str) -> list[Lead]:
    leads = []
    for c in raw_companies:
        addr = c.get("registered_address_in_full") or ""
        leads.append(
            normalize_lead(
                name=c.get("name", "Unknown"),
                country_code=(c.get("jurisdiction_code") or "").split("_")[0],
                country_name=country_name,
                region=default_region,
                segment=segment,
                address=addr or None,
                website=None,
                source="OpenCorporates",
                source_url=c.get("opencorporates_url"),
                found_reason=f"Matched OpenCorporates company search (company number {c.get('company_number', 'n/a')}).",
            )
        )
    return leads


# --------------------------------------------------------------------------
# 2. Newbuilding-contract trackers (maritime trade press)
# --------------------------------------------------------------------------

# Loose pattern for "<Buyer> ordered/signed ... <N> ... at/with <Shipyard>"
_CONTRACT_PATTERN = re.compile(
    r"(?P<buyer>[A-Z][\w&.,' -]{2,60}?)\s+"
    r"(?:has\s+)?(?:signed(?:\s+a)?\s+contract\s+with|ordered|placed\s+an\s+order\s+(?:for|with))\s+"
    r"(?P<shipyard_or_qty>[\w&.,' -]{2,80})",
    re.IGNORECASE,
)


def scrape_newbuild_contracts(url: str) -> list[dict]:
    """Pull a newbuilding-contracts roundup page and extract loose
    (buyer, detail) signal pairs by keyword pattern matching.

    This is intentionally conservative: it flags candidate sentences for
    a human (or a Claude-drafted summary) to confirm rather than
    asserting structured shipyard/quantity fields it can't reliably
    parse from arbitrary prose. Treat every row as "needs a 30-second
    human glance," not as verified data.
    """
    _require(requests, "requests")
    _require(BeautifulSoup, "beautifulsoup4")
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    text_blocks = [p.get_text(" ", strip=True) for p in soup.find_all(["p", "li", "td"])]

    signals = []
    for block in text_blocks:
        if not re.search(r"\b(contract|order|newbuild|keel[- ]laying|steel[- ]cutting)\b", block, re.IGNORECASE):
            continue
        m = _CONTRACT_PATTERN.search(block)
        signals.append(
            {
                "date": date.today().isoformat(),
                "raw_text": block,
                "buyer_guess": m.group("buyer").strip() if m else None,
                "source": url,
            }
        )
    return signals


# --------------------------------------------------------------------------
# 3. RSS/Atom monitoring
# --------------------------------------------------------------------------

# Keep this list in two rough groups: (a) general newbuild/contract language,
# and (b) classification-agreement language. Class societies (DNV, ABS,
# Lloyd's Register, Bureau Veritas, ClassNK, RINA) get engaged right at
# project kickoff -- often before a shipyard's own contract-signing press
# release -- so a "to class" / "classification agreement" mention is
# sometimes the EARLIEST public signal a project exists at all, across any
# region (not just one country). Applies globally: whatever country the
# monitored feeds happen to cover.
NEWBUILD_KEYWORDS = (
    # general newbuild / contract signals
    "newbuild", "new build", "keel laying", "keel-laying", "steel cutting",
    "steel-cutting", "shipbuilding contract", "vessel order", "orders vessel",
    "signs contract", "signed a contract", "orderbook",
    # classification-agreement signals (often the earliest public signal,
    # since class gets assigned at project kickoff)
    "to class", "classification agreement", "class notation", "classed by",
    "assigned class", "class society", "newbuilding series", "approval in principle",
    "dnv", "lloyd's register", "bureau veritas", "classnk", "class nk", "rina class",
)


def _clean_summary(raw: str | None, max_len: int = 220) -> str | None:
    """Strip HTML and collapse whitespace from an RSS <description>, so the
    dashboard can show a short, readable excerpt instead of raw markup."""
    if not raw:
        return None
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    # Some feeds append "The post ... appeared first on ..." boilerplate to
    # the description -- trim it so the excerpt reads like an actual summary.
    text = re.sub(r"\s*The post .* appeared first on .*$", "", text).strip()
    if not text:
        return None
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
    return text


def _extract_image(entry: dict) -> str | None:
    """Best-effort image URL for an RSS entry, checked against real feed
    output from several maritime outlets. Not every feed publishes one
    (e.g. gCaptain's doesn't) -- this returns None rather than guessing."""
    thumbs = entry.get("media_thumbnail") or []
    if thumbs and thumbs[0].get("url"):
        return thumbs[0]["url"]

    for media in entry.get("media_content") or []:
        media_type = (media.get("type") or "").lower()
        if media.get("url") and (media.get("medium") == "image" or media_type.startswith("image")):
            return media["url"]

    for enc in entry.get("enclosures") or []:
        enc_type = (enc.get("type") or "").lower()
        href = enc.get("href") or enc.get("url")
        if href and (not enc_type or enc_type.startswith("image")):
            return href

    for link in entry.get("links") or []:
        if link.get("rel") == "enclosure" and (link.get("type") or "").startswith("image") and link.get("href"):
            return link["href"]

    return None


def monitor_rss_feeds(feed_urls: list[str]) -> list[dict]:
    _require(feedparser, "feedparser")
    hits = []
    for feed_url in feed_urls:
        parsed = feedparser.parse(feed_url)
        for entry in parsed.entries:
            haystack = f"{entry.get('title', '')} {entry.get('summary', '')}".lower()
            if any(kw in haystack for kw in NEWBUILD_KEYWORDS):
                hits.append(
                    {
                        "title": entry.get("title"),
                        "link": entry.get("link"),
                        "published": entry.get("published", entry.get("updated")),
                        "source": feed_url,
                        "summary": _clean_summary(entry.get("summary")),
                        "image": _extract_image(entry),
                    }
                )
    return hits


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _cmd_opencorporates(args):
    raw = search_opencorporates(args.keyword, args.jurisdiction, api_token=args.token)
    leads = opencorporates_to_leads(raw, args.country_name, args.region, args.segment)
    tree = build_dashboard_tree(leads)
    _write(tree, args.output)
    print(f"Wrote {len(leads)} leads from OpenCorporates to {args.output}")


def _cmd_newbuild_scrape(args):
    signals = scrape_newbuild_contracts(args.url)
    _write(signals, args.output)
    print(f"Wrote {len(signals)} candidate newbuild signals to {args.output}")


def _cmd_rss(args):
    hits = monitor_rss_feeds(args.feeds)
    _write(hits, args.output)
    print(f"Wrote {len(hits)} matching RSS entries to {args.output}")


def _write(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="C-TORQ compliant lead-sourcing pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p1 = sub.add_parser("opencorporates", help="Search OpenCorporates for companies")
    p1.add_argument("--keyword", required=True, help='e.g. "shipyard", "marine equipment"')
    p1.add_argument("--jurisdiction", required=True, help="OpenCorporates jurisdiction code, e.g. 'no', 'kr', 'ae', 'sg'")
    p1.add_argument("--country-name", required=True)
    p1.add_argument("--region", required=True, help="Region/state label to bucket results under")
    p1.add_argument("--segment", default="Uncategorised — needs review")
    p1.add_argument("--token", default=None, help="OpenCorporates api_token (or set OPENCORPORATES_API_TOKEN)")
    p1.add_argument("--output", default="opencorporates_leads.json")
    p1.set_defaults(func=_cmd_opencorporates)

    p2 = sub.add_parser("newbuild-scrape", help="Scan a newbuilding-contracts roundup page for signal sentences")
    p2.add_argument("--url", required=True)
    p2.add_argument("--output", default="newbuild_signals.json")
    p2.set_defaults(func=_cmd_newbuild_scrape)

    p3 = sub.add_parser("rss-monitor", help="Keyword-filter maritime press RSS feeds for newbuild signals")
    p3.add_argument("--feeds", nargs="+", required=True)
    p3.add_argument("--output", default="rss_signals.json")
    p3.set_defaults(func=_cmd_rss)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
