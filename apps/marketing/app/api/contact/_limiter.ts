/**
 * Sliding-window rate limiter for /api/contact.
 *
 * Three buckets:
 *   - per-IP:    5 submissions / hour   (normal humans don't repeat-submit)
 *   - per-email: 3 submissions / 24h    (dedupe accidental double-submits)
 *   - global:    100 submissions / min  (absolute sanity ceiling)
 *
 * Lives in a sibling module rather than route.ts because Next 15's App
 * Router rejects non-route exports from a `route.ts` file. Tests import
 * the reset hook from here.
 */

export const RATE_LIMITS = {
  perIp: { max: 5, windowMs: 60 * 60 * 1000 },
  perEmail: { max: 3, windowMs: 24 * 60 * 60 * 1000 },
  global: { max: 100, windowMs: 60 * 1000 },
} as const;

const ipHits = new Map<string, number[]>();
const emailHits = new Map<string, number[]>();
const globalHits: number[] = [];

function pruneAndCount(hits: number[], now: number, windowMs: number): number {
  while (hits.length > 0 && now - hits[0] > windowMs) {
    hits.shift();
  }
  return hits.length;
}

export function checkAndRecordIp(ip: string, now: number): boolean {
  return checkAndRecord(ipHits, ip, now, RATE_LIMITS.perIp);
}

export function checkAndRecordEmail(email: string, now: number): boolean {
  return checkAndRecord(emailHits, email, now, RATE_LIMITS.perEmail);
}

export function checkAndRecordGlobal(now: number): boolean {
  const count = pruneAndCount(globalHits, now, RATE_LIMITS.global.windowMs);
  if (count >= RATE_LIMITS.global.max) return false;
  globalHits.push(now);
  return true;
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

export function resetForTests(): void {
  ipHits.clear();
  emailHits.clear();
  globalHits.length = 0;
}
