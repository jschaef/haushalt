import { describe, expect, it } from "vitest";
import { MIN_LENGTH, isPasswordProblem, localProblems, passwordLength, problemMessage } from "./password";

describe("password hints", () => {
  it("counts characters, not UTF-16 units", () => {
    expect(passwordLength("äöü")).toBe(3);
    expect(passwordLength("😀😀")).toBe(2);
    // NFKC: the ligature "ﬁ" counts as "fi"
    expect(passwordLength("ﬁ")).toBe(2);
  });

  it("asks for the minimum length", () => {
    expect(localProblems("a".repeat(MIN_LENGTH - 1), "")).toEqual(["too_short"]);
    expect(localProblems("Kassenbon-Sommer-2026", "")).toEqual([]);
    expect(localProblems("x".repeat(129), "")).toEqual(["too_long"]);
  });

  it("checks the confirmation only once something is typed", () => {
    expect(localProblems("Kassenbon-Sommer-2026", "Kassenbon")).toEqual(["mismatch"]);
    expect(localProblems("Kassenbon-Sommer-2026", "Kassenbon-Sommer-2026")).toEqual([]);
  });

  it("maps API reasons to messages", () => {
    expect(isPasswordProblem("common")).toBe(true);
    expect(isPasswordProblem("something")).toBe(false);
    expect(problemMessage("personal")).toBe("password.personal");
  });
});
