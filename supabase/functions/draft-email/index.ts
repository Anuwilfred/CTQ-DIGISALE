// C·TORQ — AI email drafting proxy (Supabase Edge Function)
//
// Writes ONE draft cold-outreach email for a company/contact in the
// Pipeline. It never sends anything — it only returns a subject + body for
// a person to review, edit, and explicitly approve in the app. Sending is
// a separate function (send-email) that only fires on a separate, later
// click, so nothing goes out without a human looking at it first.
//
// Uses the same ANTHROPIC_API_KEY secret as the research function — no
// web search here, so it's cheap and fast (plain text generation only).
//
// ---- Deploy ----
//   supabase functions deploy draft-email --no-verify-jwt
//
// ---- Secrets (reuses what's already set for the research function) ----
//   ANTHROPIC_API_KEY, ALLOWED_ORIGIN — already set if you did SETUP.md steps 1-3
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

const SYSTEM_PROMPT = `You write short, professional first-touch cold outreach emails on behalf of C-TORQ, a company that supplies vessel automation, navigation, alarm monitoring (AMS), LNG cargo/fuel systems, and fire & gas safety systems to shipyards and ship operators worldwide.

You will be given facts about one specific company/contact: their name, segment, which of C-TORQ's system categories are relevant to them, and optionally a sales note. Write ONE email that:
- Has a short, specific, non-spammy subject line (never "Introduction" or "Partnership Opportunity" — reference something concrete about the recipient's business instead).
- Opens with one sentence that shows you know who they are and what they build/operate — no generic flattery.
- States, in 1-2 sentences, the ONE most relevant capability C-TORQ offers them based on their categories (e.g. automation -> integrated vessel automation/control systems; navigation -> navigation & bridge systems; safety -> fire & gas detection systems; cargo with LNG relevance -> LNG cargo/fuel handling systems). Do not list every category — pick what's most relevant and be specific and technical, not generic marketing language.
- Ends with a low-friction call to action (e.g. asking for a short call, or offering to send technical specs) — never pushy.
- Signs off with "[Your name]" as a literal placeholder — never invent a sender name.
- Is under 150 words total, plain text (no markdown, no bullet points, no emoji), and sounds like a real engineer/salesperson wrote it, not an AI.

Respond with ONLY one JSON object, no markdown fences, no extra prose:
{"subject": "string", "body": "string with \\n for line breaks"}`;

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
    return jsonResponse({ error: "Server is missing ANTHROPIC_API_KEY." }, 500);
  }

  let body: any;
  try {
    body = await req.json();
  } catch {
    return jsonResponse({ error: "Invalid JSON body" }, 400);
  }

  const companyName = String(body?.companyName || "").trim().slice(0, 200);
  const contactName = String(body?.contactName || "").trim().slice(0, 100);
  const contactRole = String(body?.contactRole || "").trim().slice(0, 100);
  const segment = String(body?.segment || "").trim().slice(0, 400);
  const categories = Array.isArray(body?.categories) ? body.categories.slice(0, 10) : [];
  const notes = String(body?.notes || "").trim().slice(0, 500);

  if (!companyName) {
    return jsonResponse({ error: 'Missing "companyName"' }, 400);
  }

  const facts = [
    `Company: ${companyName}`,
    contactName ? `Contact: ${contactName}${contactRole ? " (" + contactRole + ")" : ""}` : "Contact: not named — address the company generally",
    segment ? `What they do: ${segment}` : "",
    categories.length ? `Relevant C-TORQ categories: ${categories.join(", ")}` : "",
    notes ? `Sales note: ${notes}` : "",
  ].filter(Boolean).join("\n");

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
        max_tokens: 600,
        system: SYSTEM_PROMPT,
        messages: [{ role: "user", content: facts }],
      }),
    });

    const data = await anthropicRes.json();
    if (!anthropicRes.ok) {
      return jsonResponse({ error: data?.error?.message || "Anthropic API error" }, 502);
    }

    const content: any[] = Array.isArray(data.content) ? data.content : [];
    const rawText = content.filter((b) => b.type === "text").map((b) => b.text).join("\n").trim();

    let parsed: any;
    try {
      const jsonMatch = rawText.match(/\{[\s\S]*\}/);
      parsed = JSON.parse(jsonMatch ? jsonMatch[0] : rawText);
    } catch {
      return jsonResponse({ error: "Could not parse draft as JSON", raw: rawText.slice(0, 500) }, 502);
    }

    return jsonResponse({ subject: parsed.subject || "", body: parsed.body || "" }, 200);
  } catch (err) {
    return jsonResponse({ error: String(err) }, 500);
  }
});
