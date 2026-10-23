// Category keys are internal ids (the API allows ^[a-z0-9_]{2,48}$). People
// type names, so the form turns whatever is typed into a valid key.
export const KEY_RE = /^[a-z0-9_]{2,48}$/;

const UMLAUTS: Record<string, string> = { ä: "ae", ö: "oe", ü: "ue", ß: "ss" };

export function toCategoryKey(text: string): string {
  return text
    .toLowerCase()
    .replace(/[äöüß]/g, (c) => UMLAUTS[c])
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "") // accents: é -> e
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 48)
    .replace(/_+$/, "");
}

// the typed key wins; without one the German name gives the key
export function effectiveKey(key: string, nameDe: string): string {
  return toCategoryKey(key.trim() ? key : nameDe);
}
