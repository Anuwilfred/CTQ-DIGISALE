// C·TORQ — email sending proxy (Supabase Edge Function)
//
// Sends ONE email through a Gmail account, using an "app password" so the
// real Gmail password never has to be stored anywhere. This function is
// only ever called after a person has reviewed an AI-drafted email in the
// app and clicked "Approve", then clicked a SEPARATE "Send" button — there
// is no path from draft straight to sent without both explicit clicks.
//
// ---- Deploy ----
//   supabase functions deploy send-email --no-verify-jwt
//
// ---- Secrets ----
//   supabase secrets set GMAIL_ADDRESS=you@gmail.com
//   supabase secrets set GMAIL_APP_PASSWORD=xxxxxxxxxxxxxxxx   (16-char app password, NOT your real Gmail password)
//   supabase secrets set SENDER_NAME="Your Name"               (optional, shown as the "From" display name)
//   ALLOWED_ORIGIN — already set if you did SETUP.md steps 1-3
//
// How to get a Gmail app password: SETUP.md at the repo root, Step 6.

import nodemailer from "npm:nodemailer@^9";

const GMAIL_ADDRESS = Deno.env.get("GMAIL_ADDRESS");
const GMAIL_APP_PASSWORD = Deno.env.get("GMAIL_APP_PASSWORD");
const SENDER_NAME = Deno.env.get("SENDER_NAME") || "C·TORQ";
const ALLOWED_ORIGIN = Deno.env.get("ALLOWED_ORIGIN") || "https://anuwilfred.github.io";

const CORS_HEADERS: Record<string, string> = {
  "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
  });
}

function isValidEmail(s: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s);
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: CORS_HEADERS });
  }
  if (req.method !== "POST") {
    return jsonResponse({ error: "POST only" }, 405);
  }
  if (!GMAIL_ADDRESS || !GMAIL_APP_PASSWORD) {
    return jsonResponse(
      { error: "Server is missing GMAIL_ADDRESS / GMAIL_APP_PASSWORD. See SETUP.md Step 6." },
      500,
    );
  }

  let body: any;
  try {
    body = await req.json();
  } catch {
    return jsonResponse({ error: "Invalid JSON body" }, 400);
  }

  const to = String(body?.to || "").trim();
  const subject = String(body?.subject || "").trim().slice(0, 300);
  const text = String(body?.body || "").trim().slice(0, 5000);
  const replyTo = String(body?.replyTo || "").trim();

  if (!isValidEmail(to)) {
    return jsonResponse({ error: "Missing or invalid \"to\" address" }, 400);
  }
  if (!subject || !text) {
    return jsonResponse({ error: "Missing subject or body" }, 400);
  }

  const transport = nodemailer.createTransport({
    host: "smtp.gmail.com",
    port: 465,
    secure: true,
    auth: {
      user: GMAIL_ADDRESS,
      pass: GMAIL_APP_PASSWORD,
    },
  });

  try {
    const info = await transport.sendMail({
      from: `"${SENDER_NAME}" <${GMAIL_ADDRESS}>`,
      to,
      subject,
      text,
      replyTo: replyTo && isValidEmail(replyTo) ? replyTo : undefined,
    });
    return jsonResponse({ sent: true, messageId: info?.messageId || null }, 200);
  } catch (err) {
    return jsonResponse({ sent: false, error: String(err) }, 502);
  }
});
