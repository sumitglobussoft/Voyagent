"use client";

/**
 * LocaleProvider — client-side i18n context.
 *
 * Reads the ``voyagent_locale`` cookie on mount and exposes the
 * resolved locale plus a ``t(key, vars?)`` translator function to any
 * descendant client component via ``useTranslations``.
 *
 * Server components should NOT go through this context — they call
 * ``getMessages(locale)`` directly from ``lib/i18n``. The context
 * exists solely so that interactive widgets (command palette,
 * LocaleSwitcher, etc.) can render localized strings without a
 * prop-drilling cascade.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  DEFAULT_LOCALE,
  LOCALE_COOKIE,
  getMessages,
  isLocale,
  translate,
  type Locale,
  type Messages,
} from "@/lib/i18n";

type LocaleContextValue = {
  locale: Locale;
  messages: Messages;
  t: (key: string, vars?: Record<string, string | number>) => string;
  setLocale: (next: Locale) => void;
};

const LocaleContext = createContext<LocaleContextValue | null>(null);

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const row = document.cookie
    .split("; ")
    .find((r) => r.startsWith(`${name}=`));
  return row ? row.slice(name.length + 1) : null;
}

function writeCookie(name: string, value: string): void {
  if (typeof document === "undefined") return;
  document.cookie = `${name}=${value}; path=/; max-age=${60 * 60 * 24 * 365}; SameSite=Lax`;
}

export function LocaleProvider({
  children,
  initialLocale,
}: {
  children: ReactNode;
  initialLocale?: Locale;
}) {
  const [locale, setLocaleState] = useState<Locale>(
    initialLocale ?? DEFAULT_LOCALE,
  );

  // Re-read the cookie on mount so an SSR-rendered tree stays in
  // sync with whatever the browser actually has stored.
  useEffect(() => {
    const fromCookie = readCookie(LOCALE_COOKIE);
    if (fromCookie && isLocale(fromCookie) && fromCookie !== locale) {
      setLocaleState(fromCookie);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setLocale = useCallback((next: Locale) => {
    writeCookie(LOCALE_COOKIE, next);
    setLocaleState(next);
    // Server components must re-render to pick up the new dictionary,
    // so a full reload is the honest thing to do here.
    if (typeof window !== "undefined") {
      window.location.reload();
    }
  }, []);

  const value = useMemo<LocaleContextValue>(() => {
    const messages = getMessages(locale);
    return {
      locale,
      messages,
      t: (key, vars) => translate(messages, key, vars),
      setLocale,
    };
  }, [locale, setLocale]);

  return (
    <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>
  );
}

export function useTranslations(): LocaleContextValue {
  const ctx = useContext(LocaleContext);
  if (!ctx) {
    // Soft fallback so a component mounted outside the provider
    // (tests, storybook, etc.) still renders something useful.
    const messages = getMessages(DEFAULT_LOCALE);
    return {
      locale: DEFAULT_LOCALE,
      messages,
      t: (key, vars) => translate(messages, key, vars),
      setLocale: () => {
        /* no-op outside provider */
      },
    };
  }
  return ctx;
}
