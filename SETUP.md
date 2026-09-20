# Setting up live AI search (Anthropic + Supabase)

The "Research desk" box at the top of the **Active projects** tab lets you
type in a company, shipyard, vessel or project name and get Claude to
search the live web for it — real current status, whether a competitor's
automation/navigation/safety system has already been awarded, and any
published procurement contact.

The app itself is a static site (GitHub Pages), so it can't hold your
Anthropic API key safely — anyone could view the page source and steal it.
Instead, the key lives in a small **Supabase Edge Function** that the app
calls; the function calls Anthropic on the app's behalf and only ever
returns the finished answer. This is a one-time setup, done outside of
this chat since it needs your own accounts and keys.

## What this will cost

Every click of "Search live" makes one Claude API call with web search
turned on. With the default model (Haiku 4.5) and up to 6 searches per
request, a typical search costs roughly **$0.01–0.03**. Supabase's free
tier easily covers the Edge Function hosting itself. You only pay
Anthropic for what you actually use — there's no fixed monthly fee unless
you add one.

## Step 1 — Get an Anthropic API key

1. Go to [console.anthropic.com](https://console.anthropic.com) and sign in
   (or create an account).
2. Add a small amount of credit under **Billing**.
3. Go to **API Keys** → **Create Key**. Copy it — you'll paste it once into
   Supabase in Step 3, never into this app's code or into this chat.

## Step 2 — Create a Supabase project (skip if you already have one)

1. Go to [supabase.com](https://supabase.com) and sign in / create an
   account (free tier is fine).
2. Click **New project**, give it a name (e.g. `ctorq-sales`), pick a
   region close to you, and wait ~2 minutes for it to spin up.
3. In the project dashboard, go to **Project Settings → API**. You'll need
   two values from this page for Step 4:
   - **Project URL** (looks like `https://xxxxxxxx.supabase.co`)
   - **anon public** key (a long string starting with `eyJ...`)

## Step 3 — Deploy the Edge Function

The function's code is already written and sitting in this repo at
`supabase/functions/research/index.ts`. From a terminal, on a machine with
the repo cloned:

```bash
npm install -g supabase        # one-time, if you don't have the CLI
supabase login                 # opens a browser to authorize
supabase link --project-ref xxxxxxxx      # the xxxxxxxx from your Project URL
supabase secrets set ANTHROPIC_API_KEY=sk-ant-your-real-key-here
supabase secrets set ALLOWED_ORIGIN=https://anuwilfred.github.io
supabase functions deploy research --no-verify-jwt
```

If that succeeds, your function is live at:

```
https://xxxxxxxx.supabase.co/functions/v1/research
```

(No local Supabase CLI? You can also paste `supabase/functions/research/index.ts`
into a new Edge Function through the Supabase dashboard's function editor —
**Edge Functions → Create a new function** — and set the same two secrets
under **Project Settings → Edge Functions → Secrets**.)

## Step 4 — Point the app at it

**Easiest way:** open the app itself, go to the **Settings** tab, paste the
Project URL and anon public key from Step 2 into "Backend connection", and
click **Save connection**. That's it — no code edit or push needed, and it
takes effect immediately in that browser.

**Or, to set it as the default for everyone** (so a fresh visitor is
connected without touching Settings), edit the code directly:
Open `index.html` in this repo and find this block near the top of the
`<script>` section:

```js
var CONFIG = {
  RESEARCH_URL: '',
  RESEARCH_ANON_KEY: ''
};
```

Fill in the two values from Steps 2 and 3:

```js
var CONFIG = {
  RESEARCH_URL: 'https://xxxxxxxx.supabase.co/functions/v1/research',
  RESEARCH_ANON_KEY: 'eyJ...your-anon-public-key...'
};
```

Save, commit, and push (or upload through the GitHub web UI as usual). The
Research desk box will detect the config and switch from "Live search
isn't connected yet" to "Connected."

### C-TORQ company profile (for better email drafts)

Also on the **Settings** tab is a "C-TORQ company profile" card — a place
to paste C-TORQ's real website and a short paragraph of real
differentiators (what C-TORQ actually delivers, real references, what
sets it apart from a yard's current/preferred supplier, certifications,
turnaround times, etc.). Once saved, every AI-drafted outreach email uses
these real facts to talk specifically about C-TORQ's own capabilities,
instead of a generic category description — and the AI is explicitly told
that C-TORQ is the solution provider sending the email, never the
recipient. This is stored only in this browser (like the backend
connection above) and sent along with each drafting request.

**"Study our website" button:** instead of writing the About-us paragraph
by hand, paste C-TORQ's website address and click **Study our website**.
This actually visits the real site — the homepage plus up to ~11 of its
most relevant internal pages (about, products, services, etc.) — reads
the real text on them, and drafts a factual summary of what C-TORQ
actually does, straight from that content (never invented). The draft
appears below for review; nothing is saved until you click **Use this
text** (copies it into the About-us box) and then the separate **Save
profile** button. This needs one more Edge Function deployed, using the
same secrets you already set in Steps 1–3 — no new keys needed:

```bash
supabase functions deploy study-website --no-verify-jwt
```

(Or, without the CLI: paste `supabase/functions/study-website/index.ts`
into a new Edge Function through the Supabase dashboard, same as the
no-CLI option in Step 3.) The app finds it automatically once
`RESEARCH_URL` is set, since it lives right next to the other functions
in the same Supabase project.

## Step 5 — turn on automatic daily AI research (no clicking required)

Once Steps 1–4 are done, the app can also research on its own, every day,
without anyone opening the app or clicking anything. A GitHub Actions job
(`.github/workflows/ai-research-daily.yml`, already in this repo) runs
once a day, asks the same backend from Step 3 about a **fixed list of ~28
real shipyards, systems suppliers, classification-agreement, and discovery
queries** (`scripts/ai_research_daily.py`), and automatically adds any
genuinely new, still-open opportunity it finds straight into the Active
Projects tab — skipping anything where a competitor's systems have
already been publicly awarded.

The list includes queries specifically hunting for classification-society
agreements (DNV, ABS, Lloyd's Register, Bureau Veritas, ClassNK, RINA) —
class gets assigned right at project kickoff, often before a shipyard's
own contract-signing press release, so it's frequently the earliest
public sign a project exists at all. These run globally, across any
region — not restricted to one country.

That fixed list is the important part: it means the automatic side of the
app makes the same small, known number of Anthropic calls every day —
about 28 — no matter how many people are using the app or clicking
"Search live" that day. The two don't add up to some unpredictable
runaway number; automatic research has its own fixed daily budget
(roughly $0.45–$0.85/day, so still well under $30/month on its own),
completely separate from whatever ad-hoc searching your team does by
hand. The RSS lead-sourcing job (`.github/workflows/lead-sourcing.yml`)
also now watches for classification-agreement language in the maritime
trade press feeds it already monitors, at no extra API cost since that
job is pure keyword-matching, not an AI call.

To turn it on, add two **repository secrets** (Settings → Secrets and
variables → Actions → New repository secret) using the same two values
from Step 4:

- `RESEARCH_URL` — your Supabase function URL
- `RESEARCH_ANON_KEY` — your Supabase anon public key

That's it — the workflow already exists and is scheduled; it just needs
those two secrets to stop no-op-ing. You can also trigger it manually any
time from the repo's **Actions** tab → "AI research (daily, automatic)" →
**Run workflow**, to see it work immediately rather than waiting for the
next scheduled run.

### Company discovery (grows the directory itself, not just projects)

Until now, the company directory (the list you browse in Pipeline) only
grew when someone researched and added a company by hand — unlike Active
Projects above, it never discovered new prospects on its own. A second
daily job (`.github/workflows/company-discovery-daily.yml`, running
`scripts/discover_companies_daily.py`) closes that gap: it asks the same
backend about a fixed, bounded watchlist of company **types** and regions
(e.g. "marine automation integrator in Dubai, UAE," "vessel owner in
Singapore") and adds any real, genuinely-new company it confirms straight
into `data/companies.json`.

Every company this adds is tagged `needsReview: true` and shows a "Needs
review" badge in the app (both in the company list and its detail page),
because a single AI web-search pass isn't the same bar as the
two-independent-source check the rest of this directory was manually built
with — worth a quick glance (its own website is usually enough to confirm
it's real) before relying on it for outreach. It also refuses to invent a
brand-new country's currency/timezone/language — if a result lands in a
country not already in the directory, it's logged and skipped rather than
guessed, and you can add that country manually the same way every existing
one started.

This needs one thing beyond Steps 1–4: the `research` function was updated
to also handle `mode: "company"` alongside its existing project-research
mode, so it needs redeploying (same secrets, no new ones):

```bash
supabase functions deploy research --no-verify-jwt
```

Then add the same two repo secrets as the project-research job above if
you haven't already (`RESEARCH_URL`, `RESEARCH_ANON_KEY`) — this job reuses
them. Cost is the same shape as the project-research job: a fixed ~12
queries/day, roughly $0.15–0.30/day on top of the existing automation.

## Step 6 — turn on AI email drafting + sending (Gmail)

Once Steps 1–4 are working, every company in the Pipeline tab gets an
"Outreach email" box: click **Draft with AI** to get a personalized draft,
edit it if you want, click **Approve**, then a separate **Send email**
click actually sends it through your own Gmail account. Nothing sends
without both of those explicit clicks — there's no one-click auto-send.

This needs two more Edge Functions (already written, same repo) and a
Gmail **app password** (a 16-character password Google generates just for
this, so your real Gmail password never has to be stored anywhere).

**Get a Gmail app password:**
1. Your Google account needs **2-Step Verification** turned on first
   (myaccount.google.com/security) — turn it on if it isn't already.
2. Go to myaccount.google.com/apppasswords, sign in again if asked.
3. Type a name like "C-TORQ app" and click **Create**.
4. Google shows a 16-character password (like `abcd efgh ijkl mnop`) —
   copy it now, it's only shown once.

**Deploy the two new functions and set their secrets:**
```bash
supabase secrets set ANTHROPIC_API_KEY=sk-ant-your-real-key-here   # already set in Step 3 — same key, reused
supabase functions deploy draft-email --no-verify-jwt

supabase secrets set GMAIL_ADDRESS=you@gmail.com
supabase secrets set GMAIL_APP_PASSWORD="abcdefghijklmnop"          # the 16-char password, no spaces
supabase secrets set SENDER_NAME="Your Name"                        # optional, shown as the From name
supabase functions deploy send-email --no-verify-jwt
```

No changes needed in `index.html` for this step — the app finds these two
new functions automatically once `RESEARCH_URL` is set (Step 4), since
they live right next to the research function in the same Supabase
project.

**Cost:** drafting reuses the same Anthropic key and costs a small
fraction of a cent per draft (no web search involved, so cheaper than a
live research search). Sending itself is free — it's just going through
your own Gmail account, the same as sending from Gmail normally, so
Gmail's own daily sending limits apply (roughly 500/day for a personal
account).

### Watched websites (auto-check a company's site for news)

On the Settings tab, under "C-TORQ company profile," there's a "Watched
websites" card. Paste in any company's website (a shipyard, an integrator,
a systems supplier — anyone) and, from the next daily automatic run
onward, the same job from Step 5 will also ask the AI to check that
company for recent news, press releases or new contract/vessel
announcements — exactly like the fixed watchlist, just for sites your team
adds as you find them. No one has to notice the news themselves and type
it in; any real finding shows up in Active Projects like everything else
the daily job discovers, tagged "Watched website: &lt;name&gt;" so you can tell
where it came from.

This needs one small one-time addition to your Supabase project — a table
to hold the list of sites (so adding/removing one from Settings never
needs a code push). In the Supabase dashboard, go to **SQL Editor** and
run:

```sql
create table public.watched_sources (
  id bigint generated always as identity primary key,
  url text not null,
  label text,
  added_at timestamptz not null default now()
);

alter table public.watched_sources enable row level security;

create policy "public read"   on public.watched_sources for select using (true);
create policy "public insert" on public.watched_sources for insert with check (true);
create policy "public delete" on public.watched_sources for delete using (true);
```

That's it — no new secrets, no new Edge Function, no new deploy. The
Settings tab talks to this table directly using the same anon public key
already saved in Backend connection. As with the anon key generally
(see Notes on safety below), these policies mean anyone with the app's
public key could technically add or remove rows here too; if that becomes
a concern, tighten the insert/delete policies in Supabase later — ask and
this can be adjusted.

### Save a discovered company (turns a search into a directory entry)

Both the Research Desk (top box on the Projects tab — checks a named
company/project) and Discover a company (the box below it — finds a new
company you don't have a name for yet) can now show a **Save to
directory** button under a result, with an **Also watch this website**
checkbox next to it.

"Also watch this website" is instant — it just adds a row to the
`watched_sources` table above, so make sure that table already exists
first. "Save to directory" is not instant: the app is a static site with
no server of its own, so it can't write to `data/companies.json` directly.
Instead it saves the company into a small holding table, and the daily
company-discovery job (the one from the "Company discovery" section above)
folds it into the real directory within a day, tagged `needsReview: true`
exactly like the automatic watchlist finds — a single AI pass isn't the
same bar as this directory's normal two-source check.

This needs one more one-time table, alongside `watched_sources`:

```sql
create table public.pending_companies (
  id bigint generated always as identity primary key,
  name text not null,
  website text,
  city text,
  country text,
  segment text,
  categories jsonb not null default '[]'::jsonb,
  contact jsonb,
  sources jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

alter table public.pending_companies enable row level security;

create policy "public read"   on public.pending_companies for select using (true);
create policy "public insert" on public.pending_companies for insert with check (true);
```

No delete policy is needed for the app itself — only the daily job removes
rows (via a service-level call from GitHub Actions), once they've been
merged into `data/companies.json` or turned out to be a duplicate. A saved
company whose country isn't tracked yet in the directory is deliberately
left in this table rather than dropped, so it's still there once you add
that country manually — check the table in the Supabase dashboard if a
save doesn't show up in the directory after a day or two.

The Research Desk's project-mode search doesn't normally know a company's
website/city/country (only company-discovery mode originally did) — the
app works around this itself now, so no redeploy is required for this to
work: when you click Save on a Research Desk result with no website, it
quietly runs one extra company-mode lookup by name first to fill in the
gaps before saving. You'll briefly see "Looking up its website and
location…" under the button when this happens. If that extra lookup can't
confirm a real company either, the save still goes through but says so
plainly, since it likely won't be placeable in the directory without a
website/country to go on.

### Job-category tags (Services tab)

Tapping a job-category tile on the Services tab shows every company (and
new signal) that matches, with a "+ Add" button next to each one so you can
tag a company to that category yourself. Tagging now saves permanently: as
soon as you tap it, the app writes the company's full category list into a
small holding table (the same pattern as `watched_sources` and
`pending_companies` above) so it's there the next time anyone opens the
app, and the daily company-discovery job (Step 5's "Company discovery"
section) folds it into the real `data/companies.json` within a day.

This needs one more one-time table, alongside `watched_sources` and
`pending_companies`:

```sql
create table public.category_overrides (
  company_id text primary key,
  categories jsonb not null default '[]'::jsonb,
  updated_at timestamptz not null default now()
);

alter table public.category_overrides enable row level security;

create policy "public read"   on public.category_overrides for select using (true);
create policy "public insert" on public.category_overrides for insert with check (true);
create policy "public update" on public.category_overrides for update using (true) with check (true);
create policy "public delete" on public.category_overrides for delete using (true);
```

If this table doesn't exist yet, tagging still works for the rest of your
current session (same as before) — it just won't be remembered after a
refresh until you run the SQL above once. Once the daily job has applied a
tag to `data/companies.json`, it removes that row from the table, so
`category_overrides` should normally only ever hold whatever's been tagged
since the last run — check it in the Supabase dashboard if a tag doesn't
seem to be sticking.

New signals (the raw, unreviewed items from the RSS feed) can also be
tagged from this same panel, but that tag is session-only and isn't saved
anywhere, since signals themselves get replaced wholesale by tomorrow's
automated run — there's no stable record for a saved tag to attach to.

## Notes on safety

- The **anon key** is meant to be public — Supabase issues it specifically
  for use in client-side code, so it's fine that it ends up visible in
  `index.html`.
- The **Anthropic API key** never appears in `index.html`, the GitHub repo,
  or this chat — it only lives as a Supabase secret on their servers.
- Because the anon key is public, anyone who finds your app's page source
  could technically call the function too, which would use your Anthropic
  credit. If that becomes a concern, Supabase supports adding simple rate
  limiting or an allow-list at the Edge Function level — ask and this can
  be added later.
