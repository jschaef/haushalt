import { describe, expect, it } from "vitest";
import { EMPTY_FILTER, activeConditions, euroCents, reportQuery } from "./report";

describe("euroCents", () => {
  it("reads German and English amounts", () => {
    expect(euroCents("12,50")).toBe(1250);
    expect(euroCents("12.5")).toBe(1250);
    expect(euroCents("1.234,56 €")).toBe(123456);
    expect(euroCents("7")).toBe(700);
  });
  it("leaves out what is no amount", () => {
    expect(euroCents("")).toBeNull();
    expect(euroCents("abc")).toBeNull();
    expect(euroCents("-5")).toBeNull();
    expect(euroCents("1,234")).toBeNull();
  });
});

describe("reportQuery", () => {
  it("sends only what is set", () => {
    expect(reportQuery(EMPTY_FILTER).toString()).toBe("range=30d");
    expect(activeConditions(EMPTY_FILTER)).toBe(0);
  });
  it("sends OR values, NOT flags, text, amounts and the group", () => {
    const filter = {
      ...EMPTY_FILTER,
      range: "custom" as const,
      custom: { start: "2026-01-01", end: "" },
      flow: "spending" as const,
      sources: ["bank" as const, "fixed" as const],
      categories: { ids: [3, 5], not: false },
      tags: { ids: [7], not: true },
      // NOT without values is no condition
      stores: { ids: [], not: true },
      q: " Urlaub ",
      q_not: true,
      min: "10",
      max: "x",
    };
    const params = reportQuery(filter, "month");
    expect(params.get("start")).toBe("2026-01-01");
    expect(params.has("end")).toBe(false);
    expect(params.getAll("source")).toEqual(["bank", "fixed"]);
    expect(params.getAll("category_id")).toEqual(["3", "5"]);
    expect(params.has("category_not")).toBe(false);
    expect(params.getAll("tag_id")).toEqual(["7"]);
    expect(params.get("tag_not")).toBe("true");
    expect(params.has("store_not")).toBe(false);
    expect(params.get("q")).toBe("Urlaub");
    expect(params.get("q_not")).toBe("true");
    expect(params.get("min_cents")).toBe("1000");
    expect(params.has("max_cents")).toBe(false);
    expect(params.get("group")).toBe("month");
    expect(activeConditions(filter)).toBe(6);
  });
});
