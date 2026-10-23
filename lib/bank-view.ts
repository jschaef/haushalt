import type { BankTransaction, Category, Recurring } from "@/lib/api";

// Sorting and filtering of the bank list. A booking's category is its own
// (counts itself) or that of its fixed cost; a receipt booking has none here
// (receipts have a category per line, not per booking).

export type SortKey = "date_desc" | "date_asc" | "amount_desc" | "amount_asc" | "counterparty" | "category" | "fixed";
export const SORT_KEYS: SortKey[] = ["date_desc", "date_asc", "amount_desc", "amount_asc", "counterparty", "category", "fixed"];

// "none": bookings without a category
export type CategoryFilter = number | "none" | null;

type Context = { categories: Category[]; recurring: Recurring[]; locale: string };

export function bookingCategoryId(booking: BankTransaction, recurring: Recurring[]): number | null {
  if (booking.status === "counted") return booking.category_id;
  if (booking.status === "fixed") return recurring.find((r) => r.id === booking.recurring_id)?.category_id ?? null;
  return null;
}

export function bookingYears(bookings: BankTransaction[]): number[] {
  return [...new Set(bookings.map((b) => Number(b.booked_on.slice(0, 4))))].sort((a, b) => b - a);
}

export function filterBookings(
  bookings: BankTransaction[],
  { category, year }: { category: CategoryFilter; year: number | null },
  recurring: Recurring[],
): BankTransaction[] {
  return bookings.filter((b) => {
    if (year !== null && Number(b.booked_on.slice(0, 4)) !== year) return false;
    if (category === null) return true;
    const id = bookingCategoryId(b, recurring);
    return category === "none" ? id === null : id === category;
  });
}

export function sortBookings(bookings: BankTransaction[], key: SortKey, { categories, recurring, locale }: Context): BankTransaction[] {
  const collator = new Intl.Collator(locale, { sensitivity: "base", numeric: true });
  const categoryName = (b: BankTransaction) => {
    const c = categories.find((x) => x.id === bookingCategoryId(b, recurring));
    return c ? (locale === "de" ? c.name_de : c.name_en) : "";
  };
  const fixedName = (b: BankTransaction) => (b.status === "fixed" ? (recurring.find((r) => r.id === b.recurring_id)?.name ?? "") : "");
  // newest first as the tie-breaker, and empty names last
  const byDate = (a: BankTransaction, b: BankTransaction) => b.booked_on.localeCompare(a.booked_on) || b.id - a.id;
  const byText = (name: (b: BankTransaction) => string) => (a: BankTransaction, b: BankTransaction) => {
    const [x, y] = [name(a), name(b)];
    if (!x !== !y) return x ? -1 : 1;
    return collator.compare(x, y) || byDate(a, b);
  };
  const compare: Record<SortKey, (a: BankTransaction, b: BankTransaction) => number> = {
    date_desc: byDate,
    date_asc: (a, b) => -byDate(a, b),
    // biggest spending first: the most negative amount
    amount_desc: (a, b) => a.amount_cents - b.amount_cents || byDate(a, b),
    amount_asc: (a, b) => b.amount_cents - a.amount_cents || byDate(a, b),
    counterparty: byText((b) => b.counterparty),
    category: byText(categoryName),
    fixed: byText(fixedName),
  };
  return [...bookings].sort(compare[key]);
}
