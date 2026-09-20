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
