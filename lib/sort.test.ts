import { describe, expect, it } from "vitest";
import { byName } from "./sort";

describe("byName", () => {
  it("sorts alphabetically, case and umlauts as people expect", () => {
    const items = ["Wohnen", "abos", "Ärzte", "Lebensmittel", "Zoo"].map((name) => ({ name }));
    expect(byName(items, (i) => i.name, "de").map((i) => i.name)).toEqual(["abos", "Ärzte", "Lebensmittel", "Wohnen", "Zoo"]);
  });

  it("compares numbers by value and leaves the input alone", () => {
    const items = [{ name: "Zähler 10" }, { name: "Zähler 2" }];
    expect(byName(items, (i) => i.name, "de").map((i) => i.name)).toEqual(["Zähler 2", "Zähler 10"]);
    expect(items[0].name).toBe("Zähler 10");
  });
});
