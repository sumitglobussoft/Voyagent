"use client";

/**
 * ThemeProvider — dark-mode context.
 *
 * Reads `voyagent_theme` cookie (values: "light" | "dark" | "system") on
 * mount and applies `class="dark"` to `<html>`. When the user toggles,
 * both the cookie and `localStorage` are updated so the preference
 * survives full reloads and server-rendered pages. "system" resolves
 * against `prefers-color-scheme` and re-resolves if the OS flips it.
 *
 * The cookie is the source of truth for the server (so a future RSC
 * branch can read it) — localStorage is a fast-path mirror for client
 * rehydration before the cookie round-trip completes.
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

export type ThemeMode = "light" | "dark" | "system";

type ThemeContextValue = {
  theme: ThemeMode;
  /** The currently-applied theme after resolving "system". */
  resolved: "light" | "dark";
  setTheme: (next: ThemeMode) => void;
  toggle: () => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

const COOKIE_NAME = "voyagent_theme";
const STORAGE_KEY = "voyagent_theme";

function readCookie(): ThemeMode | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${COOKIE_NAME}=`));
  if (!match) return null;
  const value = match.slice(COOKIE_NAME.length + 1);
  if (value === "light" || value === "dark" || value === "system") return value;
  return null;
}

function writeCookie(value: ThemeMode): void {
  if (typeof document === "undefined") return;
  // 1 year, site-wide, lax — not a security surface.
  document.cookie = `${COOKIE_NAME}=${value}; path=/; max-age=${60 * 60 * 24 * 365}; SameSite=Lax`;
}

function systemPrefersDark(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function applyClass(resolved: "light" | "dark"): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  if (resolved === "dark") root.classList.add("dark");
  else root.classList.remove("dark");
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  // Default to "system" on first render — the effect below will hydrate
  // from cookie/localStorage once the client mounts.
  const [theme, setThemeState] = useState<ThemeMode>("system");
  const [resolved, setResolved] = useState<"light" | "dark">("light");

  // Hydrate from cookie (preferred) or localStorage on mount.
  useEffect(() => {
    const fromCookie = readCookie();
    const fromStorage =
      typeof window !== "undefined"
        ? (window.localStorage.getItem(STORAGE_KEY) as ThemeMode | null)
        : null;
    const initial = fromCookie ?? fromStorage ?? "system";
    setThemeState(initial);
  }, []);

  // Resolve "system" → light/dark and apply class whenever `theme` flips.
  useEffect(() => {
    const next = theme === "system" ? (systemPrefersDark() ? "dark" : "light") : theme;
    setResolved(next);
    applyClass(next);

    if (theme !== "system" || typeof window === "undefined") return;
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const listener = (e: MediaQueryListEvent) => {
      const r: "light" | "dark" = e.matches ? "dark" : "light";
      setResolved(r);
      applyClass(r);
    };
    mql.addEventListener("change", listener);
    return () => mql.removeEventListener("change", listener);
  }, [theme]);

  const setTheme = useCallback((next: ThemeMode) => {
    setThemeState(next);
    writeCookie(next);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, next);
    }
  }, []);

  const toggle = useCallback(() => {
    // Pragmatic toggle: ignore "system" and flip between light/dark.
    setTheme(resolved === "dark" ? "light" : "dark");
  }, [resolved, setTheme]);

  const value = useMemo<ThemeContextValue>(
    () => ({ theme, resolved, setTheme, toggle }),
    [theme, resolved, setTheme, toggle],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme must be used within <ThemeProvider>");
  }
  return ctx;
}
