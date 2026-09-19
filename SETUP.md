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
