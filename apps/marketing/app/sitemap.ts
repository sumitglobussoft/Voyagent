import type { MetadataRoute } from "next";

import { DOC_SLUGS, absoluteUrl } from "@/lib/site";

const STATIC_PATHS = [
  "/",
  "/product",
  "/features",
  "/architecture",
  "/integrations",
  "/security",
  "/pricing",
  "/about",
  "/contact",
  "/changelog",
  "/domains/ticketing-visa",
  "/domains/hotels-holidays",
  "/domains/accounting",
  "/docs/api",
];

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  const docPaths = DOC_SLUGS.map((slug) => `/docs/${slug}`);
  return [...STATIC_PATHS, ...docPaths].map((path) => ({
    url: absoluteUrl(path),
    lastModified: now,
    changeFrequency: "monthly",
    priority: path === "/" ? 1 : 0.7,
  }));
}
