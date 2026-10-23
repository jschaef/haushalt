// Themes of next-themes (class on <html>, styles in app/globals.css).
// "contrast" and "contrast-light" are the low-vision modes: maximum contrast,
// larger text, no transparency or motion - on black or on white.
export const THEMES = ["light", "dark", "contrast", "contrast-light"] as const;
export type Theme = (typeof THEMES)[number];

export function isContrast(theme: string | undefined): boolean {
  return theme === "contrast" || theme === "contrast-light";
}

// Light <-> dark, staying in the low-vision mode when it is on.
export function toggledLightness(theme: string | undefined): Theme {
  switch (theme) {
    case "light":
      return "dark";
    case "contrast":
      return "contrast-light";
    case "contrast-light":
      return "contrast";
    default:
      return "light";
  }
}

// Into the low-vision mode on the same lightness, or back to the theme used
// before it (`previous`).
export function toggledContrast(theme: string | undefined, previous: string | null): string {
  if (isContrast(theme)) return previous && !isContrast(previous) ? previous : theme === "contrast-light" ? "light" : "dark";
  return theme === "light" ? "contrast-light" : "contrast";
}
