"use client";

import { createContext, use, useCallback, useMemo, useState, type ReactNode } from "react";
import { type Locale, type MessageKey, translate } from "@/lib/i18n/messages";

type I18n = {
  locale: Locale;
  t: (key: MessageKey, vars?: Record<string, string | number>) => string;
  setLocale: (locale: Locale) => void;
};

const I18nContext = createContext<I18n | null>(null);

// The locale comes from the cookie (read by the root layout on the server),
// so the first render is already in the right language.
export function I18nProvider({ initialLocale, children }: { initialLocale: Locale; children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);
  const setLocale = useCallback((next: Locale) => {
    document.cookie = `haushalt_locale=${next}; path=/; max-age=31536000; samesite=lax`;
    document.documentElement.lang = next;
    setLocaleState(next);
  }, []);
  const value = useMemo<I18n>(
    () => ({ locale, setLocale, t: (key, vars) => translate(locale, key, vars) }),
    [locale, setLocale],
  );
  return <I18nContext value={value}>{children}</I18nContext>;
}

export function useI18n(): I18n {
  const context = use(I18nContext);
  if (!context) throw new Error("useI18n outside I18nProvider");
  return context;
}
