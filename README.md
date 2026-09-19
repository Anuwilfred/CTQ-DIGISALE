# C-TORQ AI Sales Agent

Everything lives loose in this one folder — deploy this whole folder to
Vercel and it's the live app; push this whole folder to GitHub and
everything's backed up. Only `data/` is a subfolder, for the pieces that
change often.

## What's here

- **`index.html`** — the whole app: country → region → company drill-down,
  client-journey brain map, and the analytics tab.
- **`manifest.json`**, **`service-worker.js`**, **`vercel.json`** — what
  makes `index.html` installable on a phone/PC and load instantly.
- **`icon-192.png`**, **`icon-512.png`**, **`apple-touch-icon.png`**,
  **`favicon-32.png`** — the app icon.
- **`lead_sourcing.py`** — the compliant lead-sourcing script
  (OpenCorporates, newbuilding-contract press, RSS monitoring). Run it on a
  machine with normal internet access.
- **`DEPLOY-ctorq-app.md`** — how to deploy this folder to Vercel.
- **`data/companies.json`** — **the one file that actually changes as the
  business runs.** Country-based customer data, contacts, progress
  (pipeline stage + history), and local (country-specific) facts. The app
  reads this file at startup.
- **`data/schema.md`** — what every field in `companies.json` means.
- **`data/market_signals_sample.json`**, **`data/prospect_candidates_sample.json`**
  — real example output from `lead_sourcing.py`.

## Full architecture doc

The complete plan — data model, AI email-drafting pipeline, compliance
notes, cost estimates, roadmap — lives in the "C-TORQ AI Sales Agent —
Architecture & Build Plan" Claude Doc, kept up to date alongside this repo.

## Next steps (in order)

1. `git push` this folder to GitHub (already committed locally — just needs
   your sign-in to finish it).
2. Deploy this whole folder to Vercel (see `DEPLOY-ctorq-app.md`). Confirm
   it installs on a phone and PC.
3. Create a free Supabase project and the `companies` table from the
   architecture doc's schema.
4. Point `lead_sourcing.py`'s output and `index.html` at Supabase instead of
   `data/companies.json`, so every update is live everywhere instantly
   instead of needing an export + commit.
5. Wire up email sending (Resend) and meeting scheduling (Cal.com / Google
   Meet) per the architecture doc.
