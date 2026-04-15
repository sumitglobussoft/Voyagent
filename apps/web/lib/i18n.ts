/**
 * Hand-rolled i18n layer for the voyagent web app.
 *
 * Zero-dependency: messages are plain JSON dictionaries, and the
 * helpers below are thin wrappers around the browser/Node built-in
 * `Intl` APIs. Server components should call ``getMessages(locale)``
 * directly; client components should use the ``useTranslations`` hook
 * exposed by ``LocaleProvider``.
 *
 * Locale detection order (see ``detectLocale``):
 *   1. ``voyagent_locale`` cookie
 *   2. ``Accept-Language`` header (first tag prefix we support)
 *   3. fallback to ``en``
 */
import enMessages from "@/messages/en.json";
import hiMessages from "@/messages/hi.json";

export type Locale = "en" | "hi";
export const SUPPORTED_LOCALES: readonly Locale[] = ["en", "hi"] as const;
export const DEFAULT_LOCALE: Locale = "en";
export const LOCALE_COOKIE = "voyagent_locale";

export type Messages = Record<string, string>;

const DICTIONARIES: Record<Locale, Messages> = {
  en: enMessages as Messages,
  hi: hiMessages as Messages,
};

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (SUPPORTED_LOCALES as readonly string[]).includes(value);
}

/**
 * Synchronously return the message dictionary for the given locale.
 * Unknown locales fall back to English.
 */
export function getMessages(locale: string | undefined | null): Messages {
  if (locale && isLocale(locale)) return DICTIONARIES[locale];
  return DICTIONARIES[DEFAULT_LOCALE];
}

/**
 * Look up a key against a dictionary, interpolating ``{var}`` tokens.
 * Missing keys return the key itself so missing translations are
 * obvious at runtime instead of silently rendering blank.
 */
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

/**
 * Resolve a locale from the three supported sources. ``cookie`` and
 * ``acceptLanguage`` are both optional — pass whichever the current
 * surface can read.
 */
export function detectLocale(
  cookie?: string | null,
  acceptLanguage?: string | null,
): Locale {
  if (cookie && isLocale(cookie)) return cookie;
  if (acceptLanguage) {
    const tags = acceptLanguage
      .split(",")
      .map((t) => t.split(";")[0]?.trim().toLowerCase() ?? "")
      .filter(Boolean);
    for (const tag of tags) {
      const prefix = tag.split("-")[0];
      if (isLocale(prefix)) return prefix;
    }
  }
  return DEFAULT_LOCALE;
}

function bcp47(locale: string | undefined): string {
  if (locale === "hi") return "hi-IN";
  return "en-US";
}

export function formatCurrency(
  amount: string | number,
  currency: string,
  locale?: string,
): string {
  const n = typeof amount === "string" ? Number(amount) : amount;
  if (!Number.isFinite(n)) return String(amount);
  try {
    return new Intl.NumberFormat(bcp47(locale), {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(n);
  } catch {
    return `${currency} ${n}`;
  }
}

function toDate(value: Date | string): Date {
  return value instanceof Date ? value : new Date(value);
}

export function formatDate(value: Date | string, locale?: string): string {
  const d = toDate(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return new Intl.DateTimeFormat(bcp47(locale), {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(d);
}

export function formatDateTime(
  value: Date | string,
  locale?: string,
): string {
  const d = toDate(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return new Intl.DateTimeFormat(bcp47(locale), {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
}

/**
 * "5 min ago" / "2h ago" / "3d ago" style relative time. Uses
 * ``Intl.RelativeTimeFormat`` so Hindi naturally localizes.
 */
export function formatRelative(
  value: Date | string,
  locale?: string,
  now: Date = new Date(),
): string {
  const d = toDate(value);
  if (Number.isNaN(d.getTime())) return String(value);
  const diffSec = Math.round((d.getTime() - now.getTime()) / 1000);
  const abs = Math.abs(diffSec);
  const rtf = new Intl.RelativeTimeFormat(bcp47(locale), { numeric: "auto" });
  if (abs < 60) return rtf.format(diffSec, "second");
  if (abs < 3600) return rtf.format(Math.round(diffSec / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diffSec / 3600), "hour");
  if (abs < 2_592_000) return rtf.format(Math.round(diffSec / 86400), "day");
  if (abs < 31_536_000)
    return rtf.format(Math.round(diffSec / 2_592_000), "month");
  return rtf.format(Math.round(diffSec / 31_536_000), "year");
}
