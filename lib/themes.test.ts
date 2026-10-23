import { describe, expect, it } from "vitest";
import { isContrast, toggledContrast, toggledLightness } from "./themes";

describe("themes", () => {
  it("knows both low-vision modes", () => {
    expect(isContrast("contrast")).toBe(true);
    expect(isContrast("contrast-light")).toBe(true);
    expect(isContrast("light")).toBe(false);
    expect(isContrast(undefined)).toBe(false);
  });

  it("switches lightness and stays in the low-vision mode", () => {
    expect(toggledLightness("light")).toBe("dark");
    expect(toggledLightness("dark")).toBe("light");
    expect(toggledLightness(undefined)).toBe("light");
    expect(toggledLightness("contrast")).toBe("contrast-light");
    expect(toggledLightness("contrast-light")).toBe("contrast");
  });

  it("enters the low-vision mode on the same lightness", () => {
    expect(toggledContrast("light", null)).toBe("contrast-light");
    expect(toggledContrast("dark", null)).toBe("contrast");
    expect(toggledContrast(undefined, null)).toBe("contrast");
  });

  it("leaves to the previous theme, else to the matching one", () => {
    expect(toggledContrast("contrast", "light")).toBe("light");
    expect(toggledContrast("contrast-light", "dark")).toBe("dark");
    expect(toggledContrast("contrast-light", null)).toBe("light");
    expect(toggledContrast("contrast", "contrast-light")).toBe("dark");
  });
});
