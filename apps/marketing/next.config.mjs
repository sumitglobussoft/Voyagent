import { withSentryConfig } from "@sentry/nextjs";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  experimental: {
    // The /docs/[slug] route reads files from the repo `docs/` directory at
    // build/request time. Nothing else is needed; MDX is resolved via
    // next-mdx-remote at request time in a server component.
  },
};

export default withSentryConfig(
  nextConfig,
  {
    silent: true,
    org: process.env.SENTRY_ORG,
    project: process.env.SENTRY_PROJECT_MARKETING,
  },
  {
    widenClientFileUpload: true,
    transpileClientSDK: false,
    tunnelRoute: "/monitoring",
    hideSourceMaps: true,
  },
);
