import { describe, expect, it } from "vitest";
import { KEY_RE, effectiveKey, toCategoryKey } from "./category-key";

describe("category keys", () => {
  it("turns names into valid keys", () => {
    expect(toCategoryKey("Lotto")).toBe("lotto");
    expect(toCategoryKey("Essen gehen")).toBe("essen_gehen");
    expect(toCategoryKey("Müll & Gebühren")).toBe("muell_gebuehren");
    expect(toCategoryKey("Straße")).toBe("strasse");
    expect(toCategoryKey("Café-Besuche")).toBe("cafe_besuche");
    expect(toCategoryKey("  Kfz (Auto) 2  ")).toBe("kfz_auto_2");
    expect(toCategoryKey("already_ok")).toBe("already_ok");
  });

  it("stays within the length the API allows", () => {
    const key = toCategoryKey("Sehr lange Kategorie ".repeat(5));
    expect(key.length).toBeLessThanOrEqual(48);
    expect(KEY_RE.test(key)).toBe(true);
  });

  it("gives nothing valid for text without letters or digits", () => {
    expect(toCategoryKey("!!!")).toBe("");
    expect(KEY_RE.test(toCategoryKey("x"))).toBe(false); // too short
  });

  it("uses the German name when no key is typed", () => {
    expect(effectiveKey("", "Lotto")).toBe("lotto");
    expect(effectiveKey("  ", "Lotto")).toBe("lotto");
    expect(effectiveKey("Gluecksspiel", "Lotto")).toBe("gluecksspiel");
  });
});
