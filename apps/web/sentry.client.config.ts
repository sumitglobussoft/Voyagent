/**
 * Browser-side Sentry init for the authenticated web app.
 *
 * No-op when NEXT_PUBLIC_SENTRY_DSN is unset — local dev + CI stay quiet.
 */
import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT ?? "production",
    release: process.env.NEXT_PUBLIC_VOYAGENT_VERSION ?? "0.0.0-dev",
    tracesSampleRate: Number(
      process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE ?? "0.1",
    ),
    replaysOnErrorSampleRate: 0,
    replaysSessionSampleRate: 0,
    sendDefaultPii: false,
    beforeSend: scrubEvent,
    beforeBreadcrumb: scrubBreadcrumb,
  });
}

const SENSITIVE_HEADERS = new Set([
  "authorization",
  "cookie",
  "set-cookie",
  "x-api-key",
  "proxy-authorization",
]);
const SENSITIVE_COOKIES = new Set(["voyagent_at", "voyagent_rt"]);
const JWT_RE = /eyJ[A-Za-z0-9_-]+?\.[A-Za-z0-9_-]+?\.[A-Za-z0-9_-]+/g;
const REDACTED = "[scrubbed]";

function scrubString(value: unknown): unknown {
  if (typeof value !== "string") return value;
  return value.replace(JWT_RE, REDACTED);
}

function scrubHeaders(headers: Record<string, unknown> | undefined) {
  if (!headers) return headers;
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(headers)) {
    out[k] = SENSITIVE_HEADERS.has(k.toLowerCase()) ? REDACTED : scrubString(v);
  }
  return out;
}

function scrubCookies(cookieHeader: string | undefined): string | undefined {
  if (!cookieHeader) return cookieHeader;
  return cookieHeader
    .split(";")
    .map((pair) => {
      const [name, ...rest] = pair.split("=");
      const trimmed = (name ?? "").trim();
      if (SENSITIVE_COOKIES.has(trimmed)) return `${trimmed}=${REDACTED}`;
      return `${trimmed}=${rest.join("=")}`;
    })
    .join("; ");
}

function scrubEvent(event: Sentry.ErrorEvent): Sentry.ErrorEvent | null {
  if (event.request?.headers) {
    event.request.headers = scrubHeaders(
      event.request.headers as Record<string, unknown>,
    ) as typeof event.request.headers;
  }
  if (event.request?.cookies) {
    event.request.cookies = Object.fromEntries(
      Object.keys(event.request.cookies).map((k) => [
        k,
        SENSITIVE_COOKIES.has(k) ? REDACTED : event.request!.cookies![k],
      ]),
    ) as typeof event.request.cookies;
  }
  return event;
}

function scrubBreadcrumb(
  breadcrumb: Sentry.Breadcrumb,
): Sentry.Breadcrumb | null {
  const data = breadcrumb.data as Record<string, unknown> | undefined;
  if (data) {
    if (data.headers) {
      data.headers = scrubHeaders(data.headers as Record<string, unknown>);
    }
    if (typeof data.cookie === "string") {
      data.cookie = scrubCookies(data.cookie);
    }
    if (typeof data.url === "string") {
      data.url = scrubString(data.url) as string;
    }
  }
  return breadcrumb;
}
