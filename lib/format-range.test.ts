import { describe, expect, it } from "vitest";
import { validCustomRange } from "./format";

describe("validCustomRange", () => {
  const today = "2026-10-27";
  it("needs a start up to today", () => {
    expect(validCustomRange("", "", today)).toBe(false);
    expect(validCustomRange("2026-10-01", "", today)).toBe(true);
    expect(validCustomRange("2026-10-28", "", today)).toBe(false);
  });
  it("needs the end on or after the start", () => {
    expect(validCustomRange("2026-10-10", "2026-10-10", today)).toBe(true);
    expect(validCustomRange("2026-10-10", "2026-10-05", today)).toBe(false);
    // a later end is fine: the API stops at today
    expect(validCustomRange("2026-10-10", "2026-12-31", today)).toBe(true);
  });
});
