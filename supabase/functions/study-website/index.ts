// C·TORQ — "study our website" proxy (Supabase Edge Function)
//
// Actually crawls C-TORQ's own website (the homepage plus a handful of the
// most relevant-looking internal pages — about/products/services/etc.),
// strips each page down to plain text, and asks Claude to read all of it
// and write a factual summary of what C-TORQ actually does, its real
// products/services, differentiators, certifications and target
// customers. That summary is returned to the app as a DRAFT for a person
// to review and edit on the Settings tab — it is never saved or used
// automatically. Once a person approves it (clicks "Use this text" then
// "Save profile"), it becomes the real grounding fed into every AI-drafted
// outreach email — see draft-email/index.ts and COMPANY_PROFILE in
// index.html.
//
// This does NOT use Claude's web-search tool — it fetches the real pages
// itself (cheaper, and reads C-TORQ's actual current site content rather
// than whatever a search index has cached), then makes one plain
// (non-search) Claude call to summarize the fetched text. Same secrets as
// draft-email, no new ones needed.
//
// ---- Deploy ----
//   supabase functions deploy study-website --no-verify-jwt
//
// ---- Secrets (reuses what's already set for research / draft-email) ----
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

const MAX_PAGES = 12; // homepage + up to 11 more — bounded so this can't run away in cost or time
const MAX_CHARS_PER_PAGE = 4000; // plain-text characters kept per page after stripping HTML
const FETCH_TIMEOUT_MS = 8000;
const USER_AGENT = "CTORQ-WebsiteStudy/1.0 (+reads our own company's public pages to brief our sales AI)";

// Pages likely to actually describe capabilities get crawled first, since
// MAX_PAGES caps how many we fetch — no point spending the budget on a
// careers page or a blog post if there's an actual "products" page.
const PRIORITY_HINTS = [
  "about", "product", "solution", "service", "capabilit", "what-we-do",
  "portfolio", "system", "technology", "company", "why-us", "why-choose",
  "reference", "case-stud", "certif", "industr", "expertise",
];

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
  });
}

function stripHtmlToText(html: string): string {
  let text = html
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<(br|p|div|li|h[1-6]|section|article|tr)[^>]*>/gi, "\n")
    .replace(/<[^>]+>/g, " ");
  text = text
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&#39;|&apos;/g, "'")
    .replace(/&quot;/g, '"');
  text = text.replace(/[ \t]+/g, " ").replace(/\n\s*\n+/g, "\n").trim();
  return text;
}

function extractLinks(html: string, baseUrl: URL): string[] {
  const links = new Set<string>();
  const re = /<a\s+[^>]*href\s*=\s*["']([^"'#]+)["']/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html))) {
    try {
      const abs = new URL(m[1], baseUrl);
      if (abs.hostname !== baseUrl.hostname) continue; // same-domain only
      if (/\.(pdf|jpg|jpeg|png|gif|svg|zip|docx?|xlsx?|mp4|css|js)$/i.test(abs.pathname)) continue;
      abs.hash = "";
      links.add(abs.toString());
    } catch {
      // ignore malformed hrefs
    }
  }
  return Array.from(links);
}

function priorityScore(url: string): number {
  const lower = url.toLowerCase();
  for (let i = 0; i < PRIORITY_HINTS.length; i++) {
    if (lower.includes(PRIORITY_HINTS[i])) return PRIORITY_HINTS.length - i;
  }
  return 0;
}

async function fetchPage(url: string): Promise<string | null> {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
    const res = await fetch(url, {
      headers: { "User-Agent": USER_AGENT, "Accept": "text/html" },
      signal: controller.signal,
    });
    clearTimeout(timer);
    if (!res.ok) return null;
    const contentType = res.headers.get("content-type") || "";
    if (!contentType.includes("text/html")) return null;
    return await res.text();
  } catch {
    return null;
  }
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

  const rawUrl = String(body?.url || "").trim();
  if (!rawUrl) {
    return jsonResponse({ error: 'Missing "url"' }, 400);
  }

  let homeUrl: URL;
  try {
    homeUrl = new URL(/^https?:\/\//i.test(rawUrl) ? rawUrl : "https://" + rawUrl);
  } catch {
    return jsonResponse({ error: "That doesn't look like a valid URL" }, 400);
  }

  const homeHtml = await fetchPage(homeUrl.toString());
  if (!homeHtml) {
    return jsonResponse({
      error: `Couldn't reach ${homeUrl.hostname} — the site may block automated requests, or the URL may be wrong. Try pasting the exact address from your browser, or fill in "About us" by hand instead.`,
    }, 502);
  }

  const pages: { url: string; text: string }[] = [
    { url: homeUrl.toString(), text: stripHtmlToText(homeHtml).slice(0, MAX_CHARS_PER_PAGE) },
  ];

  const candidateLinks = extractLinks(homeHtml, homeUrl)
    .filter((u) => u !== homeUrl.toString())
    .sort((a, b) => priorityScore(b) - priorityScore(a))
    .slice(0, MAX_PAGES - 1);

  for (const link of candidateLinks) {
    const html = await fetchPage(link);
    if (html) {
      const text = stripHtmlToText(html);
      if (text.length > 80) { // skip near-empty pages (likely JS-rendered shells)
        pages.push({ url: link, text: text.slice(0, MAX_CHARS_PER_PAGE) });
      }
    }
  }

  const totalTextLength = pages.reduce((n, p) => n + p.text.length, 0);
  if (totalTextLength < 200) {
    return jsonResponse({
      error: `Fetched ${homeUrl.hostname} but found almost no readable text — the site may be built entirely in JavaScript (so the raw HTML has no real content to read), or it blocked this request. Fill in "About us" by hand for now, or send real page text and I can use that instead.`,
    }, 502);
  }

  const pagesForPrompt = pages
    .map((p) => `=== PAGE: ${p.url} ===\n${p.text}`)
    .join("\n\n")
    .slice(0, 60000); // hard cap regardless of page count, keeps the call cheap and fast

  const SYSTEM_PROMPT = `You are building an internal knowledge briefing for C-TORQ's own sales team, from C-TORQ's own website content pasted below. This is NOT about a prospect or competitor — every page below belongs to C-TORQ itself, the company doing the selling.

Read all the page text and write a factual, specific summary covering, where the pages actually support it:
- What C-TORQ actually does and sells (be concrete and technical, not generic marketing language)
- Specific products, systems or service lines named on the site
- Any real differentiators, certifications, standards, or track record actually stated (not invented)
- Target industries, customer types, or notable named projects/references if mentioned
- Anything else a salesperson would need to speak credibly and specifically about C-TORQ

Rules: use ONLY what the page text actually says. Never invent a capability, certification, client name or number that isn't stated. If the pages are thin on a topic, say so plainly rather than filling the gap with generic industry language. Write plain text, organized as a few short labeled paragraphs, under 700 words total. No markdown headers or bullet symbols — this will be edited by a person afterward.`;

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
        max_tokens: 1200,
        system: SYSTEM_PROMPT,
        messages: [{ role: "user", content: pagesForPrompt }],
      }),
    });

    const data = await anthropicRes.json();
    if (!anthropicRes.ok) {
      return jsonResponse({ error: data?.error?.message || "Anthropic API error" }, 502);
    }

    const content: any[] = Array.isArray(data.content) ? data.content : [];
    const summary = content.filter((b) => b.type === "text").map((b) => b.text).join("\n").trim();

    return jsonResponse({
      summary,
      pagesStudied: pages.map((p) => p.url),
      website: homeUrl.toString(),
    }, 200);
  } catch (err) {
    return jsonResponse({ error: String(err) }, 500);
  }
});
