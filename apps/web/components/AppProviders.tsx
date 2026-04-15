"use client";

/**
 * AppProviders — composes every client-side context provider that the
 * web app needs at the root of the React tree.
 *
 * Wave-2 coordination: this file is shared between the dark-mode /
 * toast polish pack (Theme + Toast) and the parallel i18n + command
 * palette agent (Locale + CommandPalette). Both agents must preserve
 * the marker comments below so the other's appends land in the right
 * place.
 *
 * Nest order (outermost → innermost):
 *   ThemeProvider > LocaleProvider > ToastProvider > CommandPaletteProvider > children
 */
import type { ReactNode } from "react";

import { CommandPaletteProvider } from "./CommandPaletteProvider";
import { LocaleProvider } from "./LocaleProvider";
import { ThemeProvider } from "./ThemeProvider";
import { ToastProvider } from "./ToastProvider";

// WAVE-2 COORDINATION MARKER — DO NOT REMOVE
// The parallel agent appends LocaleProvider + CommandPaletteProvider here.
// Nest order: outermost = Theme, then Locale, then Toast, then CommandPalette,
// then children. Both agents use the same nesting order.

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      {/* WAVE-2 COORDINATION: LocaleProvider wraps here */}
      <LocaleProvider>
        <ToastProvider>
          {/* WAVE-2 COORDINATION: CommandPaletteProvider wraps here */}
          <CommandPaletteProvider>{children}</CommandPaletteProvider>
        </ToastProvider>
      </LocaleProvider>
    </ThemeProvider>
  );
}

export default AppProviders;
