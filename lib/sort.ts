// Lists people fill themselves (categories, fixed costs, meters) are offered
// alphabetically in the user's language, not in the order they were created.
export function byName<T>(items: readonly T[], name: (item: T) => string, locale: string): T[] {
  const collator = new Intl.Collator(locale, { sensitivity: "base", numeric: true });
  return [...items].sort((a, b) => collator.compare(name(a), name(b)));
}
