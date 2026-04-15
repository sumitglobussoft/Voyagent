import { withSentryConfig } from "@sentry/nextjs";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The authenticated app is reverse-proxied at /app/* by the inner
  // nginx. Setting basePath makes Next.js emit every route AND every
  // static asset under /app/_next/* so it doesn't collide with the
  // marketing app's /_next/* assets. Server actions, <Link href>,
  // and redirect() take un-prefixed paths and the framework prepends
  // /app automatically; HTML form `action="..."` attrs are NOT
  // auto-prefixed so they must include /app explicitly.
  basePath: "/app",
};

// Sentry wrapping is a no-op at runtime if SENTRY_DSN is unset; the
// withSentryConfig call itself is cheap at build time. Source-map
// upload is only attempted when SENTRY_AUTH_TOKEN is present.
export default withSentryConfig(
  nextConfig,
  {
    silent: true,
    org: process.env.SENTRY_ORG,
    project: process.env.SENTRY_PROJECT_WEB,
  },
  {
    widenClientFileUpload: true,
    transpileClientSDK: false,
    tunnelRoute: "/monitoring",
    hideSourceMaps: true,
  },
);
