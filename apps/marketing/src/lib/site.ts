/**
 * Site-wide constants for the marketing app.
 *
 * Kept centralized so copy, URLs and nav structure only ever live in one
 * place. Page components import from here; no page owns its own nav array.
 */

export const SITE = {
  name: "Voyagent",
  category: "The Agentic Travel OS",
  tagline: "One chat. Every GDS, every accounting system, every workflow.",
  description:
    "Voyagent is an agentic operating system for travel agencies. One chat replaces ticketing, visa, hotels, holidays, and accounting work across every GDS, portal and accounting stack.",
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
] as const;

export type DocSlug = (typeof DOC_SLUGS)[number];

export const DOC_TITLES: Record<DocSlug, string> = {
  ARCHITECTURE: "Architecture",
  DECISIONS: "Decision log",
  CANONICAL_MODEL: "Canonical model",
  STACK: "Tech stack",
  ACTIVITIES: "Activity inventory",
};

export const INTEGRATION_LABELS = [
  "Amadeus",
  "Sabre",
  "Travelport",
  "TBO",
  "Riya",
  "Tally",
  "Zoho Books",
  "Busy",
  "QuickBooks",
  "SAP",
  "SAP B1",
  "Hotelbeds",
  "VFS Global",
  "BLS",
  "BSPlink",
  "Razorpay",
  "Stripe",
  "NEFT",
  "UPI",
  "RTGS",
] as const;
