import type { Locale } from "@/lib/i18n/messages";

const TAGS: Record<Locale, string> = { de: "de-DE", en: "en-GB" };

export function money(cents: number, locale: Locale, currency = "EUR", compact = false): string {
  return new Intl.NumberFormat(TAGS[locale], {
    style: "currency",
    currency,
    maximumFractionDigits: compact && Math.abs(cents) >= 100_000 ? 0 : 2,
    minimumFractionDigits: compact && Math.abs(cents) >= 100_000 ? 0 : 2,
  }).format(cents / 100);
}

// today as YYYY-MM-DD in local time (toISOString would use UTC)
export function localToday(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// a typed period the API accepts: a start, not after today, not after the end
export function validCustomRange(start: string, end: string, today: string = localToday()): boolean {
  const iso = /^\d{4}-\d{2}-\d{2}$/;
  return iso.test(start) && start <= today && (end === "" || (iso.test(end) && end >= start));
}

export function shortDate(iso: string | null, locale: Locale): string {
  if (!iso) return "";
  const [y, m, d] = iso.split("-").map(Number);
  return new Intl.DateTimeFormat(TAGS[locale], { day: "2-digit", month: "short", year: "numeric" }).format(
    new Date(Date.UTC(y, m - 1, d)),
  );
}

// "12,34" / "12.34" / "-0,25" -> cents; null for anything else
export function parseMoney(text: string): number | null {
  const cleaned = text.replace(/[\s€]/g, "");
  if (!/^-?\d+([.,]\d{1,2})?$/.test(cleaned)) return null;
  return Math.round(Number(cleaned.replace(",", ".")) * 100);
}

export function centsToInput(cents: number | null | undefined, locale: Locale): string {
  if (cents === null || cents === undefined) return "";
  const text = (cents / 100).toFixed(2);
  return locale === "de" ? text.replace(".", ",") : text;
}

export function percentChange(current: number, previous: number): number | null {
  if (!previous) return null;
  return ((current - previous) / previous) * 100;
}
