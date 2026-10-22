import { describe, expect, it } from "vitest";
import { messages, negotiate, translate } from "@/lib/i18n/messages";

describe("messages", () => {
  it("German and English have the same keys and no empty texts", () => {
    expect(Object.keys(messages.en).sort()).toEqual(Object.keys(messages.de).sort());
    for (const locale of ["de", "en"] as const) {
      for (const [key, text] of Object.entries(messages[locale])) expect(text.trim(), `${locale}:${key}`).not.toBe("");
    }
  });
  it("placeholders match between languages", () => {
    const vars = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
    for (const key of Object.keys(messages.de) as (keyof typeof messages.de)[]) {
      expect(vars(messages.en[key]), key).toEqual(vars(messages.de[key]));
    }
  });
  it("translate fills placeholders", () => {
    expect(translate("de", "receipts.read", { count: 3 })).toBe("3 Beleg(e) gelesen");
    expect(translate("en", "fixed.perDay", { amount: "€1.00" })).toBe("€1.00 per day");
  });
  it("negotiate picks a supported language", () => {
    expect(negotiate("en-US,en;q=0.9")).toBe("en");
    expect(negotiate("fr-FR,de;q=0.8")).toBe("de");
    expect(negotiate("fr")).toBe("de");
    expect(negotiate(null)).toBe("de");
  });
});
