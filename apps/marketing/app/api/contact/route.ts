import { NextResponse } from "next/server";

import {
  RATE_LIMITS,
  checkAndRecordEmail,
  checkAndRecordGlobal,
  checkAndRecordIp,
} from "./_limiter";

/**
 * /api/contact — POST handler.
 *
 * Validates shape, applies the sliding-window rate limiter (see
 * `_limiter.ts`), logs the submission to stdout, and returns
 * `{ok: true}`. Email delivery is not yet wired (SES / Resend / Postmark
 * decision pending).
 *
 * Runtime: Node (default).
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

// Cloudflare sets `cf-connecting-ip`; outer nginx forwards
// `x-forwarded-for`. Prefer cf-connecting-ip, then xff first hop, then
// the global fallback so a misbehaving proxy can't starve real users.
function clientIp(request: Request): string {
  const cf = request.headers.get("cf-connecting-ip");
  if (cf) return cf.trim();
  const xff = request.headers.get("x-forwarded-for");
  if (xff) {
    const first = xff.split(",")[0]?.trim();
    if (first) return first;
  }
  const real = request.headers.get("x-real-ip");
  if (real) return real.trim();
  return "unknown";
}

function rateLimitResponse(retryAfterSeconds: number) {
  return NextResponse.json(
    {
      ok: false,
      error:
        "Too many submissions from this source. Please wait a bit and try again.",
    },
    {
      status: 429,
      headers: { "Retry-After": String(retryAfterSeconds) },
    },
  );
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

  const now = Date.now();

  if (!checkAndRecordGlobal(now)) {
    return rateLimitResponse(Math.ceil(RATE_LIMITS.global.windowMs / 1000));
  }

  const ip = clientIp(request);
  if (!checkAndRecordIp(ip, now)) {
    return rateLimitResponse(Math.ceil(RATE_LIMITS.perIp.windowMs / 1000));
  }

  const emailKey = result.email.toLowerCase();
  if (!checkAndRecordEmail(emailKey, now)) {
    return rateLimitResponse(Math.ceil(RATE_LIMITS.perEmail.windowMs / 1000));
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
