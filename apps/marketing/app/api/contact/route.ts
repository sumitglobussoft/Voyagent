import { NextResponse } from "next/server";

/**
 * /api/contact — POST handler.
 *
 * Intentionally does NOT send email. We haven't wired an email provider
 * yet (SES, Resend, Postmark, etc. are all on the table). For now the
 * handler validates shape, logs the payload to stdout, and returns
 * `{ok: true}`. The deployment agent's log pipeline captures these
 * events; a future change swaps `console.info` for a provider call.
 *
 * Runtime: Node (default). Keeps handler minimal — no database or queue
 * dependency.
 */

export const runtime = "nodejs";

interface ContactPayload {
  name: string;
  email: string;
  company?: string;
  message: string;
}

function validate(body: unknown): ContactPayload | string {
  if (!body || typeof body !== "object") {
    return "Request body must be JSON.";
  }
  const b = body as Record<string, unknown>;
  const name = typeof b.name === "string" ? b.name.trim() : "";
  const email = typeof b.email === "string" ? b.email.trim() : "";
  const company = typeof b.company === "string" ? b.company.trim() : "";
  const message = typeof b.message === "string" ? b.message.trim() : "";
  if (!name) return "name is required.";
  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return "A valid email is required.";
  }
  if (!message) return "message is required.";
  if (message.length > 5000) return "message is too long.";
  return { name, email, company, message };
}

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { ok: false, error: "Invalid JSON." },
      { status: 400 },
    );
  }

  const result = validate(body);
  if (typeof result === "string") {
    return NextResponse.json(
      { ok: false, error: result },
      { status: 400 },
    );
  }

  // eslint-disable-next-line no-console -- structured log for deployment
  console.info("[voyagent.marketing] contact form submission", {
    receivedAt: new Date().toISOString(),
    name: result.name,
    email: result.email,
    company: result.company || null,
    messageLength: result.message.length,
  });

  return NextResponse.json({ ok: true });
}
