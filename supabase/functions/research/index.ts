// C·TORQ — live research proxy (Supabase Edge Function)
//
// This is the only place the real Anthropic API key ever lives. The app
// itself (index.html, on GitHub Pages) is a static site and cannot hold a
// secret safely — anyone could view-source it and steal the key. So the
// app calls this function instead, and this function calls Anthropic with
// the key from a server-side secret that the browser never sees.
//
// It accepts exactly one shape of request — { query, notes } — runs one
// fixed research prompt with Claude's web-search tool turned on, and
// returns strict JSON. It does not forward arbitrary prompts from the
// client, which keeps cost and abuse surface small.
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
  if (!query) {
    return jsonResponse({ error: 'Missing "query"' }, 400);
  }

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
        system: SYSTEM_PROMPT,
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
