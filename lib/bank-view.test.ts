import { describe, expect, it } from "vitest";
import type { BankTransaction, Category, Recurring } from "./api";
import { bookingCategoryId, bookingYears, filterBookings, sortBookings } from "./bank-view";

const tx = (id: number, booked_on: string, amount_cents: number, extra: Partial<BankTransaction> = {}): BankTransaction => ({
  id, booked_on, amount_cents, currency: "EUR", counterparty: "", iban: "", purpose: "", status: "review",
  account_id: null, receipt_id: null, recurring_id: null, category_id: null, settles_account_id: null, decided_by: "auto", tag_ids: [], ...extra,
});
const cat = (id: number, name_de: string): Category => ({ id, key: `k${id}`, name_de, name_en: name_de, kind: "variable", color: "#000000", icon: "" }) as Category;
const categories = [cat(1, "Scheune"), cat(2, "Abos"), cat(3, "Lebensmittel")];
const recurring = [{ id: 7, name: "Miete", category_id: 3 } as Recurring];

const list = [
  tx(1, "2025-03-01", -5000, { status: "counted", category_id: 1, counterparty: "Baumarkt" }),
  tx(2, "2026-01-10", -1200, { status: "fixed", recurring_id: 7, counterparty: "Vermieter" }),
  tx(3, "2025-12-24", -9900, { status: "review", counterparty: "zoo" }),
  tx(4, "2026-02-01", 200000, { status: "ignored", counterparty: "Arbeitgeber" }),
  tx(5, "2026-02-01", -800, { status: "counted", category_id: 2, counterparty: "Ärztekammer" }),
];
const ids = (l: BankTransaction[]) => l.map((b) => b.id);
const ctx = { categories, recurring, locale: "de" };

describe("bank view", () => {
  it("knows the category of counted and fixed bookings", () => {
    expect(bookingCategoryId(list[0], recurring)).toBe(1);
    expect(bookingCategoryId(list[1], recurring)).toBe(3);
    expect(bookingCategoryId(list[2], recurring)).toBeNull();
  });

  it("filters by category, without category and by year", () => {
    expect(ids(filterBookings(list, { category: 1, year: null }, recurring))).toEqual([1]);
    expect(ids(filterBookings(list, { category: 3, year: null }, recurring))).toEqual([2]);
    expect(ids(filterBookings(list, { category: "none", year: null }, recurring))).toEqual([3, 4]);
    expect(ids(filterBookings(list, { category: null, year: 2025 }, recurring))).toEqual([1, 3]);
    expect(bookingYears(list)).toEqual([2026, 2025]);
  });

  it("sorts by date, amount and names", () => {
    expect(ids(sortBookings(list, "date_desc", ctx))).toEqual([5, 4, 2, 3, 1]);
    expect(ids(sortBookings(list, "date_asc", ctx))).toEqual([1, 3, 2, 4, 5]);
    expect(ids(sortBookings(list, "amount_desc", ctx))).toEqual([3, 1, 2, 5, 4]);
    expect(ids(sortBookings(list, "amount_asc", ctx))).toEqual([4, 5, 2, 1, 3]);
    // German collation: "Ä" sorts like "A", so Arbeitgeber comes before Ärztekammer
    expect(ids(sortBookings(list, "counterparty", ctx))).toEqual([4, 5, 1, 2, 3]);
    // empty names last, newest first among them
    expect(ids(sortBookings(list, "category", ctx))).toEqual([5, 2, 1, 4, 3]);
    expect(ids(sortBookings(list, "fixed", ctx))[0]).toBe(2);
    expect(ids(list)).toEqual([1, 2, 3, 4, 5]); // input unchanged
  });
});
