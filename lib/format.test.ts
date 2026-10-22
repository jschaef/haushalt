import { describe, expect, it } from "vitest";
import { centsToInput, money, parseMoney, percentChange, shortDate } from "@/lib/format";

describe("money", () => {
  it("formats per locale", () => {
    expect(money(123456, "de").replace(/\s/g, " ")).toBe("1.234,56 €");
    expect(money(123456, "en")).toBe("€1,234.56");
    expect(money(-48, "de").replace(/\s/g, " ")).toBe("-0,48 €");
  });
  it("drops cents for large compact amounts", () => {
    expect(money(250000, "en", "EUR", true)).toBe("€2,500");
    expect(money(2500, "en", "EUR", true)).toBe("€25.00");
  });
});

describe("parseMoney", () => {
  it.each([
    ["12,34", 1234],
    ["12.34", 1234],
    ["-0,25", -25],
    ["7", 700],
    [" 3,5 € ", 350],
  ])("%s -> %d", (text, cents) => expect(parseMoney(text)).toBe(cents));
  it.each(["", "abc", "1,234", "1.2.3", "--1"])("rejects %s", (text) => expect(parseMoney(text)).toBeNull());
  it("round-trips centsToInput", () => {
    for (const cents of [0, 5, 99, 129, -48, 123456]) {
      expect(parseMoney(centsToInput(cents, "de"))).toBe(cents);
      expect(parseMoney(centsToInput(cents, "en"))).toBe(cents);
    }
    expect(centsToInput(null, "de")).toBe("");
  });
});

describe("dates and trends", () => {
  it("formats ISO dates without timezone shifts", () => {
    expect(shortDate("2026-01-01", "en")).toBe("01 Jan 2026");
    expect(shortDate(null, "de")).toBe("");
  });
  it("percentChange", () => {
    expect(percentChange(150, 100)).toBe(50);
    expect(percentChange(50, 100)).toBe(-50);
    expect(percentChange(10, 0)).toBeNull();
  });
});
