// C·TORQ — live research proxy (Supabase Edge Function)
//
// This is the only place the real Anthropic API key ever lives. The app
// itself (index.html, on GitHub Pages) is a static site and cannot hold a
// secret safely — anyone could view-source it and steal the key. So the
// app calls this function instead, and this function calls Anthropic with
// the key from a server-side secret that the browser never sees.
//
// It accepts { query, notes, mode } — mode is "project" (default, unchanged
// behavior: is this a real current contract/newbuild, who has the systems)
// or "company" (used by scripts/discover_companies_daily.py to grow the
// company directory itself, the same way this function already grows
// Active Projects) — runs one fixed research prompt with Claude's
// web-search tool turned on, and returns strict JSON. It does not forward
// arbitrary prompts from the client, which keeps cost and abuse surface
// small.
//
// ---- Deploy ----
//   supabase functions deploy research --no-verify-jwt
//
// ---- Secrets (set once, never put these in git) ----
//   supabase secrets set ANTHROPIC_API_KEY=sk-ant-...
//   supabase secrets set ALLOWED_ORIGIN=https://anuwilfred.github.io
//   supabase secrets set ANTHROPIC_MODEL=claude-haiku-4-5-20251001   (optional, this is the default)
//
// See SETUP.md at the repo root for the full step-by-step.

const ANTHROPIC_API_KEY = Deno.env.get("ANTHROPIC_API_KEY");
const MODEL = Deno.env.get("ANTHROPIC_MODEL") || "claude-haiku-4-5-20251001";
const ALLOWED_ORIGIN = Deno.env.get("ALLOWED_ORIGIN") || "https://anuwilfred.github.io";

const CORS_HEADERS: Record<string, string> = {
  "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const SYSTEM_PROMPT = `You are a research analyst for C-TORQ, a company that supplies vessel automation, navigation, alarm monitoring (AMS), LNG cargo/fuel systems, and fire & gas safety systems to shipyards and ship operators worldwide.

Given the name of a company, shipyard, vessel, or project, use web search to find out:
1. Whether it is a real, current (not historical/completed years ago) shipbuilding contract, newbuild program, retrofit, or company.
2. Vessel type and how many vessels, if it's a project.
3. Which shipyard is building it and which company owns/operates it.
4. Key dates: contract signing, keel-laying, launch, or delivery.
5. Whether a supplier for automation, navigation, AMS, LNG, or fire & gas safety systems has ALREADY been publicly named for this project (name them and cite it) or whether that is still open/unannounced — this determines if it's still worth contacting them now.
6. Any publicly published procurement, supply chain, or technical purchasing contact (name, role, email, phone, or supplier portal URL) for the relevant company. Never invent a name, email or phone — omit the field entirely if you can't find a real published one.
7. Which of these categories apply: automation, navigation, integration, electrical, software, cloud, safety, propulsion, cargo, hull, hvac, services.
8. For the single main company this query is really about (the owner/operator if the query names a project, or the company itself if the query names a company directly): its official website domain, headquarters city, and headquarters country. Omit any of these you can't find — never guess.

Only use information you actually found via web search and be ready to cite a source URL for each factual claim. If you cannot find real information confirming this is a genuine current project or company, say so plainly rather than guessing or inventing details.

After researching, respond with ONLY one JSON object — no markdown code fences, no extra prose before or after — matching exactly this shape:
{
  "found": true or false,
  "name": "string",
  "kind": "project" or "company",
  "summary": "2-4 sentence plain-English summary of what this is and its current status",
  "vesselType": "string or null",
  "companies": ["names of shipyards/owners/operators involved"],
  "systemsStatus": "already_awarded" or "open" or "unknown",
  "systemsAwardedTo": "string or null — who already won the automation/navigation/safety systems contract, if systemsStatus is already_awarded",
  "categories": ["subset of: automation, navigation, integration, electrical, software, cloud, safety, propulsion, cargo, hull, hvac, services"],
  "contact": {"name": "string or null", "role": "string or null", "email": "string or null", "phone": "string or null", "portalUrl": "string or null"},
  "sources": ["source URLs actually used"],
  "website": "string or null (bare domain of the main company, no https://)",
  "city": "string or null (headquarters city of the main company)",
  "country": "string or null (headquarters country of the main company, full name e.g. \\"United Arab Emirates\\")"
}`;

// mode: "company" — used to grow the company DIRECTORY itself (real
// shipyards, systems integrators, vessel owners, etc. not yet tracked),
// as distinct from mode: "project" above which grows Active Projects.
// Entries this produces are clearly marked as AI-discovered, single-pass
// web search — NOT held to the same two-independent-source bar the rest
// of the manually-researched directory uses, so the app/script surfaces
// them for a quick human glance before they're relied on for outreach.
const SYSTEM_PROMPT_COMPANY = `You are a research analyst for C-TORQ, a company that supplies vessel automation, navigation, alarm monitoring (AMS), LNG cargo/fuel systems, and fire & gas safety systems to shipyards and ship operators worldwide.

Given a description of a TYPE of company and a region (e.g. "marine automation integrator in Dubai, UAE" or "vessel owner / tanker operator headquartered in Singapore"), use web search to find ONE real, currently-operating company that matches — ideally one that is not extremely well-known/already obvious, so this surfaces genuinely new prospects rather than the same handful of famous names every time. Prefer a company you can verify is real via at least one independent source beyond its own website (a business registry, trade press, stock exchange listing, or industry directory).

Find:
1. The company's real legal/trading name.
2. Its official website domain.
3. The city and country it's headquartered in.
4. A factual 1-2 sentence description of what it actually does — concrete, not generic marketing language, similar in style to: "Shipyard — naval and commercial vessel construction, repair, maintenance, refit and conversion." or "Vessel owner/operator — owns/operates tankers and bulk carriers."
5. Which of these categories apply to what C-TORQ could sell them: automation, navigation, integration, electrical, software, cloud, safety, propulsion, cargo, hull, hvac, services.
6. Any publicly published general-inquiries or procurement contact (name/role, email, phone). Never invent one — omit the field if you can't find a real published one.

Only use information you actually found via web search. If you cannot find a real, verifiable company matching the description, say so plainly (found: false) rather than inventing one — a false negative is fine, a fabricated company is not.

After researching, respond with ONLY one JSON object — no markdown code fences, no extra prose before or after — matching exactly this shape:
{
  "found": true or false,
  "name": "string",
  "website": "string or null (bare domain, no https://)",
  "city": "string or null",
  "country": "string or null (full country name, e.g. \\"United Arab Emirates\\")",
  "segment": "1-2 sentence factual description",
  "categories": ["subset of: automation, navigation, integration, electrical, software, cloud, safety, propulsion, cargo, hull, hvac, services"],
  "contact": {"name": "string or null", "role": "string or null", "email": "string or null", "phone": "string or null"},
  "sources": ["source URLs actually used"]
}`;

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
  });
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: CORS_HEADERS });
  }
  if (req.method !== "POST") {
    return jsonResponse({ error: "POST only" }, 405);
  }
  if (!ANTHROPIC_API_KEY) {
    return jsonResponse(
      { error: "Server is missing ANTHROPIC_API_KEY. Run: supabase secrets set ANTHROPIC_API_KEY=sk-ant-..." },
      500,
    );
  }

  let body: any;
  try {
    body = await req.json();
  } catch {
    return jsonResponse({ error: 'Invalid JSON body' }, 400);
  }

  const query = String(body?.query || "").trim().slice(0, 300);
  const notes = String(body?.notes || "").trim().slice(0, 1000);
  const mode = body?.mode === "company" ? "company" : "project";
  if (!query) {
    return jsonResponse({ error: 'Missing "query"' }, 400);
  }

  const systemPrompt = mode === "company" ? SYSTEM_PROMPT_COMPANY : SYSTEM_PROMPT;
  const userMessage = notes
    ? `Research this for C-TORQ: "${query}"\n\nAdditional context from the sales team: ${notes}`
    : `Research this for C-TORQ: "${query}"`;

  try {
    const anthropicRes = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify({
        model: MODEL,
        max_tokens: 2000,
        system: systemPrompt,
        messages: [{ role: "user", content: userMessage }],
        tools: [{ type: "web_search_20250305", name: "web_search", max_uses: 6 }],
      }),
    });

    const data = await anthropicRes.json();
    if (!anthropicRes.ok) {
      return jsonResponse(
        { error: data?.error?.message || "Anthropic API error", detail: data },
        502,
      );
    }

    const content: any[] = Array.isArray(data.content) ? data.content : [];
    const rawText = content.filter((b) => b.type === "text").map((b) => b.text).join("\n").trim();

    let parsed: any;
    try {
      const jsonMatch = rawText.match(/\{[\s\S]*\}/);
      parsed = JSON.parse(jsonMatch ? jsonMatch[0] : rawText);
    } catch {
      parsed = {
        found: false,
        name: query,
        summary: "The research ran, but the answer couldn't be parsed as structured data. Raw answer: " +
          rawText.slice(0, 800),
        sources: [],
      };
    }

    // Fallback/cross-check: also surface every URL the web-search tool actually touched.
    const searchResultUrls: string[] = [];
    content.forEach((b) => {
      if (b.type === "web_search_tool_result" && Array.isArray(b.content)) {
        b.content.forEach((r: any) => { if (r?.url) searchResultUrls.push(r.url); });
      }
    });
    if (!parsed.sources || !parsed.sources.length) parsed.sources = searchResultUrls.slice(0, 8);

    parsed.usage = data.usage || null;

    return jsonResponse(parsed, 200);
  } catch (err) {
    return jsonResponse({ error: String(err) }, 500);
  }
});
