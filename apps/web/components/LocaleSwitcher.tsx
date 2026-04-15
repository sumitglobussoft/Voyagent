"use client";

/**
 * LocaleSwitcher — tiny dropdown rendered inside the settings page.
 *
 * On change it writes the ``voyagent_locale`` cookie (via the
 * LocaleProvider) and triggers a full reload so server components
 * re-render against the new dictionary.
 */
import { useTranslations } from "./LocaleProvider";
import { SUPPORTED_LOCALES, type Locale } from "@/lib/i18n";

const LABELS: Record<Locale, string> = {
  en: "English",
  hi: "हिन्दी",
};

export function LocaleSwitcher() {
  const { locale, setLocale, t } = useTranslations();
  return (
    <label
      data-testid="locale-switcher"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        fontSize: 13,
        color: "#52525b",
      }}
    >
      <span>{t("settings.language")}</span>
      <select
        aria-label={t("settings.language")}
        value={locale}
        onChange={(e) => setLocale(e.target.value as Locale)}
        style={{
          padding: "6px 10px",
          borderRadius: 6,
          border: "1px solid #d4d4d8",
          background: "#fff",
          fontSize: 13,
        }}
      >
        {SUPPORTED_LOCALES.map((l) => (
          <option key={l} value={l}>
            {LABELS[l]}
          </option>
        ))}
      </select>
    </label>
  );
}

export default LocaleSwitcher;
