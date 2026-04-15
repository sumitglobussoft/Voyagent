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
 *
 * Rate limiting: an in-process sliding-window limiter keyed by client
 * IP with a per-email daily dedup bucket and a global sanity ceiling.
 * Aggressive enough to stop a single-host flood, loose enough that a
 * real person filling the form never sees 429. The limiter lives in
 * module scope; each Next.js server process keeps its own buckets,
 * which is fine for a marketing page that runs on a single replica.
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

// ---------------------------------------------------------------------------
// Rate limiter
// ---------------------------------------------------------------------------
//
// Three buckets:
//   - per-IP:    5 submissions / hour   (normal humans don't repeat-submit)
//   - per-email: 3 submissions / 24h    (dedupe accidental double-submits)
//   - global:    100 submissions / min  (absolute sanity ceiling)
//
// Each bucket is a sliding window: we store timestamps of recent hits
// and count the ones within the window on each request. Timestamps
// older than the window are evicted to keep memory bounded. This is an
// in-memory limiter — a single process sees one view of traffic, which
// is the right trade-off for a marketing form with one replica.
//
// IP extraction: Cloudflare sets `cf-connecting-ip`, and our outer
// nginx forwards `x-forwarded-for`. We prefer cf-connecting-ip, then
// the first hop of x-forwarded-for, then fall back to the global
// bucket key so one misbehaving proxy can't starve every real user.

const RATE_LIMITS = {
  perIp: { max: 5, windowMs: 60 * 60 * 1000 }, // 5 / hour
  perEmail: { max: 3, windowMs: 24 * 60 * 60 * 1000 }, // 3 / day
  global: { max: 100, windowMs: 60 * 1000 }, // 100 / min
} as const;

const ipHits = new Map<string, number[]>();
const emailHits = new Map<string, number[]>();
const globalHits: number[] = [];

function pruneAndCount(hits: number[], now: number, windowMs: number): number {
  // Evict from the left until we hit a timestamp inside the window.
  while (hits.length > 0 && now - hits[0] > windowMs) {
    hits.shift();
  }
  return hits.length;
}

function checkAndRecord(
  map: Map<string, number[]>,
  key: string,
  now: number,
  limit: { max: number; windowMs: number },
): boolean {
  let hits = map.get(key);
  if (!hits) {
    hits = [];
    map.set(key, hits);
  }
  const count = pruneAndCount(hits, now, limit.windowMs);
  if (count >= limit.max) return false;
  hits.push(now);
  return true;
}

function checkAndRecordGlobal(now: number): boolean {
  const count = pruneAndCount(globalHits, now, RATE_LIMITS.global.windowMs);
  if (count >= RATE_LIMITS.global.max) return false;
  globalHits.push(now);
  return true;
}

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

// Exposed so tests can reset between cases.
export function __resetRateLimiterForTests(): void {
  ipHits.clear();
  emailHits.clear();
  globalHits.length = 0;
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
  if (!checkAndRecord(ipHits, ip, now, RATE_LIMITS.perIp)) {
    return rateLimitResponse(Math.ceil(RATE_LIMITS.perIp.windowMs / 1000));
  }

  const emailKey = result.email.toLowerCase();
  if (!checkAndRecord(emailHits, emailKey, now, RATE_LIMITS.perEmail)) {
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
