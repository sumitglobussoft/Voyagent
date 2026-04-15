/**
 * Site-wide constants for the marketing app.
 *
 * Kept centralized so copy, URLs and nav structure only ever live in one
 * place. Page components import from here; no page owns its own nav array.
 */

export const SITE = {
  name: "Voyagent",
  category: "The Agentic Travel OS",
  tagline:
    "The operating system for travel agencies — one chat, every vendor, zero swivel-chair work.",
  description:
    "Voyagent is the agentic operating system travel agencies have been waiting for. A single chat interface drives ticketing, visa, hotels, holidays, and accounting across every GDS, portal, and accounting stack your team already runs — with audit trails and human approvals on every side-effect.",
  // Sign-in points at the in-house auth surface inside the web app.
  // The /early-access page is still linked from elsewhere as a pitch
  // page for prospects who don't yet have a workspace.
  signInUrl: "/app/sign-in",
  signUpUrl: "/app/sign-up",
  appUrl: "/app",
  defaultOgUrl: "https://voyagent.globusdemos.com",
} as const;

export function absoluteUrl(path = "/"): string {
  const base =
    process.env.NEXT_PUBLIC_MARKETING_APP_URL ?? SITE.defaultOgUrl;
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${base}${normalized}`;
}

export const NAV_LINKS = [
  { href: "/product", label: "Product" },
  { href: "/features", label: "Features" },
  { href: "/architecture", label: "Architecture" },
  { href: "/integrations", label: "Integrations" },
  { href: "/security", label: "Security" },
  { href: "/pricing", label: "Pricing" },
  { href: "/changelog", label: "Changelog" },
  { href: "/docs/ARCHITECTURE", label: "Docs" },
] as const;

export const FOOTER_LINKS = {
  Product: [
    { href: "/product", label: "Product" },
    { href: "/features", label: "Features" },
    { href: "/architecture", label: "Architecture" },
    { href: "/integrations", label: "Integrations" },
    { href: "/security", label: "Security" },
    { href: "/pricing", label: "Pricing" },
  ],
  Company: [
    { href: "/about", label: "About" },
    { href: "/contact", label: "Contact" },
    { href: "/changelog", label: "Changelog" },
  ],
  Resources: [
    { href: "/docs/ARCHITECTURE", label: "Architecture doc" },
    { href: "/docs/DECISIONS", label: "Decision log" },
    { href: "/docs/ACTIVITIES", label: "Activity inventory" },
    { href: "/docs/CANONICAL_MODEL", label: "Canonical model" },
    { href: "/docs/STACK", label: "Tech stack" },
  ],
} as const;

export const DOC_SLUGS = [
  "ARCHITECTURE",
  "DECISIONS",
  "CANONICAL_MODEL",
  "STACK",
  "ACTIVITIES",
  "VENDOR_ONBOARDING",
] as const;

export type DocSlug = (typeof DOC_SLUGS)[number];

export const DOC_TITLES: Record<DocSlug, string> = {
  ARCHITECTURE: "Architecture",
  DECISIONS: "Decision log",
  CANONICAL_MODEL: "Canonical model",
  STACK: "Tech stack",
  ACTIVITIES: "Activity inventory",
  VENDOR_ONBOARDING: "Vendor onboarding",
};

// Convention: INTEGRATION_LABELS only lists vendors with a live driver or
// protocol layer on main today. Planned / roadmap vendors are deliberately
// excluded so the marquee never implies a relationship we don't have.
export const INTEGRATION_LABELS = [
  "Amadeus",
  "TBO",
  "Tally",
  "BSP India",
  "VFS Global",
  "Anthropic",
] as const;
