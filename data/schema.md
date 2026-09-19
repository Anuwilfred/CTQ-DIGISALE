# Data schema — `data/companies.json`

This is the interim, git-tracked data store for the C-TORQ sales pipeline.
It exists so real customer/contact/progress data has somewhere durable to
live *before* Supabase is wired up — once that happens, this file's shape
becomes the `companies` table (same fields, same nesting logic), so nothing
gets rebuilt, just migrated.

## Shape

```
{
  "schemaVersion": 1,
  "generated": "<date this snapshot was last regenerated>",
  "countries": [
    {
      "id": "no",            // short code used everywhere (URLs, IDs, filters)
      "name": "Norway",
      "regions": [
        {
          "name": "Vestland",
          "country": "no",
          "companies": [ <Company>, ... ]
        }
      ]
    }
  ]
}
```

## The `Company` record

This is the one record type that answers all four things that need saving:
**who the customer is (by country), how to contact them, what's happened so
far (progress), and country-specific facts (local data)** — plus a place for
anything typed into the app.

| Field | What it is |
|---|---|
| `id` | Stable slug (`<country>-<name>`), used as the row key everywhere |
| `name` | Company name |
| `address` | Registered/office address, as sourced |
| `website` | Company website |
| `segment` | What kind of business this is (shipbuilder, fabricator, vessel operator, etc.) |
| `source` | Where this lead was found (OpenCorporates, trade press, a directory, etc.) — always keep this; it's how a lead is defended as compliant |
| `contacts` | **Contact data.** Array of `{name, role, email, phone}`. Empty until a compliant, public contact is found — never fabricated |
| `stage` | **Progress data.** One of `found / drafted / approved / sent / replied / meeting / won / rejected` |
| `lastContact` | Date of the most recent touch |
| `nextAction` | Plain-English note on what happens next |
| `history` | **Progress data.** Ordered log of everything that's actually happened: `{type, date, text}` — `type` is one of `found / email / reply / meeting / deal / note`. This is the audit trail behind the dashboard's "client journey" brain map |
| `local` | **Local data.** Country-specific facts: `{currency, timezone, language, registrationNumber, registryNote}`. `registrationNumber` starts `null` — it only gets filled in once a real, compliant registry lookup (OpenCorporates, local company registry) confirms it. Never guessed |
| `instructions` | **App inputs.** Free-text notes or instructions a person typed into the app about this company — separate from `history` because these are *inputs to the process* (e.g. "hold outreach until Q4", "CEO prefers phone over email"), not events that happened. Array of `{date, text, by}` |

## What "processing immediately" means today vs. later

Today (git-only, no backend yet): adding a note in the app updates that
company's `instructions` and `history` in the browser tab you're using, and
the app's "Export data" button downloads the current file so it can be
committed back to this repo. That commit is the "save."

Once Supabase is connected: the app writes directly to the `companies`
table on every action (note, approval, stage change) — no export/commit
step, and every device sees the same data immediately. That's the next
piece of infrastructure needed to make "immediate" literal rather than
"immediate, then you commit it."
