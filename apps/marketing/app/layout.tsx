import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { Inter } from "next/font/google";

import { MarketingShell } from "@/components/MarketingShell";
import { SITE, absoluteUrl } from "@/lib/site";

import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  metadataBase: new URL(
    process.env.NEXT_PUBLIC_MARKETING_APP_URL ?? SITE.defaultOgUrl,
  ),
  title: {
    default: `${SITE.name} — ${SITE.category}`,
    template: `%s — ${SITE.name}`,
  },
  description: SITE.description,
  openGraph: {
    title: `${SITE.name} — ${SITE.category}`,
    description: SITE.description,
    url: absoluteUrl("/"),
    siteName: SITE.name,
    images: [
      {
        url: "/og-image.svg",
        width: 1200,
        height: 630,
        alt: `${SITE.name} — ${SITE.category}`,
      },
    ],
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: `${SITE.name} — ${SITE.category}`,
    description: SITE.tagline,
    images: ["/og-image.svg"],
  },
  icons: {
    icon: "/favicon.svg",
  },
};

export const viewport: Viewport = {
  themeColor: "#0B4F71",
};

/**
 * Root layout — wraps every page in the marketing shell.
 *
 * `<MarketingShell>` renders the nav, footer, and skip-to-content anchor;
 * pages only need to supply their page-body content. The Inter font is
 * attached to the `<html>` element so CSS variables resolve uniformly.
 */
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="font-sans bg-white text-slate-900 antialiased">
        <a href="#main" className="skip-link">
          Skip to main content
        </a>
        <MarketingShell>{children}</MarketingShell>
      </body>
    </html>
  );
}
