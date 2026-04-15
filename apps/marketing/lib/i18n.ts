/**
 * Minimal i18n helper for the marketing app.
 *
 * Marketing has no authed surface and no client-side locale switcher,
 * so this file is deliberately thinner than the web app's equivalent:
 * just ``getMessages(locale)`` + ``translate`` + locale detection.
 *
 * Marketing pages are cached aggressively by the CDN and are
 * primarily consumed in English; the Hindi dictionary exists so that
 * any localized strings we do render (e.g. a future /hi subpath) can
 * reuse the same key shape as the web app.
 */
import enMessages from "../messages/en.json";
import hiMessages from "../messages/hi.json";

export type Locale = "en" | "hi";
export const SUPPORTED_LOCALES: readonly Locale[] = ["en", "hi"] as const;
export const DEFAULT_LOCALE: Locale = "en";

export type Messages = Record<string, string>;

const DICTIONARIES: Record<Locale, Messages> = {
  en: enMessages as Messages,
  hi: hiMessages as Messages,
};

export function isLocale(value: unknown): value is Locale {
  return (
    typeof value === "string" &&
    (SUPPORTED_LOCALES as readonly string[]).includes(value)
  );
}

export function getMessages(locale: string | undefined | null): Messages {
  if (locale && isLocale(locale)) return DICTIONARIES[locale];
  return DICTIONARIES[DEFAULT_LOCALE];
}

export function translate(
  messages: Messages,
  key: string,
  vars?: Record<string, string | number>,
): string {
  const raw = messages[key] ?? key;
  if (!vars) return raw;
  return raw.replace(/\{(\w+)\}/g, (_, name: string) =>
    name in vars ? String(vars[name]) : `{${name}}`,
  );
}

export function detectLocale(acceptLanguage?: string | null): Locale {
  if (!acceptLanguage) return DEFAULT_LOCALE;
  const tags = acceptLanguage
    .split(",")
    .map((t) => t.split(";")[0]?.trim().toLowerCase() ?? "")
    .filter(Boolean);
  for (const tag of tags) {
    const prefix = tag.split("-")[0];
    if (isLocale(prefix)) return prefix;
  }
  return DEFAULT_LOCALE;
}
