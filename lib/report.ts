import type { CustomRange, Range } from "@/lib/api";

// The report's filter as query parameters (backend/haushalt_api/report_api.py).
// Jochen, 2026-10-29: AND between fields, OR within a field, NOT per field.

export type ReportSource = "receipt" | "bank" | "fixed";
export const REPORT_SOURCES: ReportSource[] = ["receipt", "bank", "fixed"];
export type ReportGroup = "none" | "month" | "category" | "tag" | "store" | "source" | "account";
export const REPORT_GROUPS: ReportGroup[] = ["none", "month", "category", "tag", "store", "source", "account"];

// several values: any of them (OR); not: none of them (NOT)
export type Choice = { ids: number[]; not: boolean };
export const NO_CHOICE: Choice = { ids: [], not: false };

export type ReportFilter = {
  range: Range;
  custom: CustomRange;
  flow: "all" | "spending" | "income";
  one_off: "exclude" | "include" | "only";
  sources: ReportSource[];
  categories: Choice;
  tags: Choice;
  stores: Choice;
  accounts: Choice;
  q: string;
  q_not: boolean;
  // euros as typed ("12,50")
  min: string;
  max: string;
};

export const EMPTY_FILTER: ReportFilter = {
  range: "30d",
  custom: { start: "", end: "" },
  flow: "all",
  one_off: "exclude",
  sources: [],
  categories: NO_CHOICE,
  tags: NO_CHOICE,
  stores: NO_CHOICE,
  accounts: NO_CHOICE,
  q: "",
  q_not: false,
  min: "",
  max: "",
};

/** "12,50", "12.5", "1.234,56" -> cents; empty or not a number -> null. */
export function euroCents(text: string): number | null {
  let value = text.trim().replace(/\s|€/g, "");
  if (!value) return null;
  // a comma is the decimal mark; dots before it group thousands
  if (value.includes(",")) value = value.replace(/\./g, "").replace(",", ".");
  if (!/^\d+(\.\d{1,2})?$/.test(value)) return null;
  return Math.round(Number(value) * 100);
}

export function reportQuery(filter: ReportFilter, group?: ReportGroup): URLSearchParams {
  const params = new URLSearchParams({ range: filter.range });
  if (filter.range === "custom") {
    params.set("start", filter.custom.start);
    if (filter.custom.end) params.set("end", filter.custom.end);
  }
  if (filter.flow !== "all") params.set("flow", filter.flow);
  if (filter.one_off !== "exclude") params.set("one_off", filter.one_off);
  for (const source of filter.sources) params.append("source", source);
  const choices: [string, Choice][] = [
    ["category", filter.categories],
    ["tag", filter.tags],
    ["store", filter.stores],
    ["account", filter.accounts],
  ];
  for (const [name, choice] of choices) {
    if (!choice.ids.length) continue;
    for (const id of choice.ids) params.append(`${name}_id`, String(id));
    if (choice.not) params.set(`${name}_not`, "true");
  }
  const q = filter.q.trim();
  if (q) {
    params.set("q", q);
    if (filter.q_not) params.set("q_not", "true");
  }
  const min = euroCents(filter.min);
  const max = euroCents(filter.max);
  if (min !== null) params.set("min_cents", String(min));
  if (max !== null) params.set("max_cents", String(max));
  if (group && group !== "none") params.set("group", group);
  return params;
}

/** How many conditions are set (for the "reset" button). */
export function activeConditions(filter: ReportFilter): number {
  return (
    (filter.flow !== "all" ? 1 : 0) +
    (filter.one_off !== "exclude" ? 1 : 0) +
    (filter.sources.length ? 1 : 0) +
    [filter.categories, filter.tags, filter.stores, filter.accounts].filter((c) => c.ids.length).length +
    (filter.q.trim() ? 1 : 0) +
    (euroCents(filter.min) !== null ? 1 : 0) +
    (euroCents(filter.max) !== null ? 1 : 0)
  );
}
