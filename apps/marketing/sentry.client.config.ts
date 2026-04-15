/**
 * Browser-side Sentry init for the marketing site.
 * Silent no-op when NEXT_PUBLIC_SENTRY_DSN is unset.
 */
import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

const SENSITIVE_HEADERS = new Set([
  "authorization",
  "cookie",
  "set-cookie",
  "x-api-key",
]);
const SENSITIVE_COOKIES = new Set(["voyagent_at", "voyagent_rt"]);
const JWT_RE = /eyJ[A-Za-z0-9_-]+?\.[A-Za-z0-9_-]+?\.[A-Za-z0-9_-]+/g;
const REDACTED = "[scrubbed]";

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT ?? "production",
    release: process.env.NEXT_PUBLIC_VOYAGENT_VERSION ?? "0.0.0-dev",
    tracesSampleRate: Number(
      process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE ?? "0.1",
    ),
    sendDefaultPii: false,
    beforeSend(event) {
      if (event.request?.headers) {
        const h = event.request.headers as Record<string, unknown>;
        for (const k of Object.keys(h)) {
          if (SENSITIVE_HEADERS.has(k.toLowerCase())) h[k] = REDACTED;
          else if (typeof h[k] === "string")
            h[k] = (h[k] as string).replace(JWT_RE, REDACTED);
        }
      }
      if (event.request?.cookies) {
        const c = event.request.cookies as Record<string, unknown>;
        for (const k of Object.keys(c)) {
          if (SENSITIVE_COOKIES.has(k)) c[k] = REDACTED;
        }
      }
      return event;
    },
  });
}
