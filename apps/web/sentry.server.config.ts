/**
 * Node-runtime Sentry init (server components, route handlers, server actions).
 *
 * Silent no-op when SENTRY_DSN / NEXT_PUBLIC_SENTRY_DSN is unset.
 */
import * as Sentry from "@sentry/nextjs";

const dsn = process.env.SENTRY_DSN ?? process.env.NEXT_PUBLIC_SENTRY_DSN;

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

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.SENTRY_ENVIRONMENT ?? "production",
    release: process.env.VOYAGENT_VERSION ?? "0.0.0-dev",
    tracesSampleRate: Number(process.env.SENTRY_TRACES_SAMPLE_RATE ?? "0.1"),
    sendDefaultPii: false,
    beforeSend(event) {
      if (event.request?.headers) {
        const headers = event.request.headers as Record<string, unknown>;
        for (const key of Object.keys(headers)) {
          if (SENSITIVE_HEADERS.has(key.toLowerCase())) {
            headers[key] = REDACTED;
          } else if (typeof headers[key] === "string") {
            headers[key] = (headers[key] as string).replace(JWT_RE, REDACTED);
          }
        }
      }
      if (event.request?.cookies) {
        const cookies = event.request.cookies as Record<string, unknown>;
        for (const key of Object.keys(cookies)) {
          if (SENSITIVE_COOKIES.has(key)) cookies[key] = REDACTED;
        }
      }
      return event;
    },
    beforeBreadcrumb(breadcrumb) {
      const data = breadcrumb.data as Record<string, unknown> | undefined;
      if (data && typeof data.url === "string") {
        data.url = data.url.replace(JWT_RE, REDACTED);
      }
      return breadcrumb;
    },
  });
}
