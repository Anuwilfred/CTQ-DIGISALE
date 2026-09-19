# Getting C·TORQ Sales Command installed as real software

`ctorq-app.zip` is a complete, tested Progressive Web App: unzip it and every
file in it (`index.html`, `manifest.json`, `service-worker.js`, `icons/`,
`vercel.json`) is ready to deploy as-is. It's the same glass/Apple-style
dashboard you already saw, just packaged so a real web address can serve it
and phones/PCs can install it — not just preview it inside Claude.

## Deploy it on Vercel (free, ~5 minutes, no credit card)

**Fastest path — Vercel CLI, no GitHub needed yet:**
1. Unzip `ctorq-app.zip` into its own folder.
2. Install Node.js if you don't have it already (nodejs.org — free).
3. Open a terminal in that folder and run:
   ```
   npx vercel
   ```
4. It'll ask you to log in (free account, email or GitHub) and confirm the
   project settings — just press Enter through the defaults, it's a static
   site so nothing needs configuring.
5. It prints a live `https://your-project.vercel.app` link. That link is
   the real installable app.

**Path that ties in with the automation you're building next — GitHub + Vercel:**
1. Create a free GitHub repo (e.g. `ctorq-sales-command`) and push the
   unzipped folder's contents to it.
2. Go to vercel.com, sign in with GitHub, click "Add New → Project", pick
   that repo, and click Deploy. No settings needed — it's static files.
3. Every time you push a change to that repo, Vercel automatically
   redeploys. This is the same repo the lead-sourcing script and its
   GitHub Actions automation will live in, so everything ends up in one
   place.

## Installing it once it's live

- **On a phone (Android/Chrome):** open the link, tap the menu, tap
  "Install app" (or you'll see a banner offering it automatically).
- **On an iPhone (Safari):** open the link, tap the Share icon, tap
  "Add to Home Screen."
- **On a PC (Chrome/Edge):** open the link, click the install icon (a
  small monitor-with-arrow) in the address bar, or the menu → "Install
  C·TORQ...".

Once installed it opens in its own window with no browser bar, has its own
app icon (the blue-to-purple "CT" mark), and reopens instantly from cache
even with a flaky connection — that's what the service worker in the zip
does.

## What's still sample data

The dashboard still shows the same fictional demo pipeline (Fjordal Marine
Yard, Hanul Heavy Marine, etc.) — installing it doesn't change that. The
next step to make it real is wiring `lead_sourcing.py`'s output (or a
Supabase table) into this page instead of the hardcoded `DATA` array in
`index.html`. Happy to do that once the app is live at a real URL and/or
Supabase is set up — just say the word.
