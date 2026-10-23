import type { MessageKey } from "@/lib/i18n/messages";

// Mirrors backend/haushalt_api/passwords.py (NIST SP 800-63B: length, no
// composition rules). The API decides; this only gives early hints.
export const MIN_LENGTH = 12;
export const MAX_LENGTH = 128;

export type PasswordProblem = "too_short" | "too_long" | "common" | "repetitive" | "personal" | "unchanged" | "mismatch";

// characters as people count them (NFKC, code points), not UTF-16 units
export function passwordLength(password: string): number {
  return [...password.normalize("NFKC")].length;
}

export function localProblems(password: string, confirm: string): PasswordProblem[] {
  const found: PasswordProblem[] = [];
  const length = passwordLength(password);
  if (length < MIN_LENGTH) found.push("too_short");
  if (length > MAX_LENGTH) found.push("too_long");
  if (confirm !== "" && confirm !== password) found.push("mismatch");
  return found;
}

const KNOWN = new Set<string>(["too_short", "too_long", "common", "repetitive", "personal", "unchanged", "mismatch"]);

export function isPasswordProblem(value: string): value is PasswordProblem {
  return KNOWN.has(value);
}

export function problemMessage(problem: PasswordProblem): MessageKey {
  return `password.${problem}` as MessageKey;
}
