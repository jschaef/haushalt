"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ChevronDown, ExternalLink, Search } from "lucide-react";
import { Tile } from "@/components/bento";
import { CustomRangeFields, RangePicker } from "@/components/dashboard";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api, spendingCategories, type Product, type PurchaseFilter, type Unit } from "@/lib/api";
import { money, shortDate, validCustomRange } from "@/lib/format";
import { useData } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n/provider";
import type { Locale, MessageKey } from "@/lib/i18n/messages";
import { byName } from "@/lib/sort";
import { cn } from "@/lib/utils";

// What was bought, from confirmed receipts (Jochen, 2026-10-28): food and
// non-food sums for the period, products with quantities, search and filters.

const SELECT_CLASS =
  "h-9 w-full min-w-0 rounded-lg border border-input bg-transparent px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50 dark:bg-input/30";
const UNITS: Unit[] = ["piece", "kg", "l"];
type Sort = "total" | "name" | "last" | "count";
const SORTS: { value: Sort; label: MessageKey }[] = [
  { value: "total", label: "purchases.sortTotal" },
  { value: "count", label: "purchases.sortCount" },
  { value: "last", label: "purchases.sortLast" },
  { value: "name", label: "purchases.sortName" },
];

function sorted(products: Product[], sort: Sort, locale: Locale): Product[] {
  const list = [...products];
  if (sort === "name") return list.sort((a, b) => a.name.localeCompare(b.name, locale));
  if (sort === "last") return list.sort((a, b) => b.last_bought.localeCompare(a.last_bought) || b.total_cents - a.total_cents);
  if (sort === "count") return list.sort((a, b) => b.lines - a.lines || b.total_cents - a.total_cents);
  return list;
}

function amount(value: number, unit: Unit, locale: Locale, t: (key: MessageKey) => string): string {
  const number = new Intl.NumberFormat(locale === "de" ? "de-DE" : "en-GB", { maximumFractionDigits: unit === "piece" ? 2 : 3 }).format(value);
  return `${number} ${t(`unit.${unit}`)}`;
}

function quantities(product: Product, locale: Locale, t: (key: MessageKey) => string): string {
  return UNITS.filter((unit) => product.quantities[unit]).map((unit) => amount(product.quantities[unit]!, unit, locale, t)).join(" · ");
}

function averages(product: Product, locale: Locale, t: (key: MessageKey) => string): string {
  return UNITS.filter((unit) => product.average_cents[unit] !== undefined)
    .map((unit) => `${money(product.average_cents[unit]!, locale)}/${t(`unit.${unit}`)}`)
    .join(" · ");
}

function ProductLines({ product, filter }: { product: Product; filter: PurchaseFilter }) {
  const { t, locale } = useI18n();
  const lines = useData(() => api.productLines(product.key, filter), `${product.key}:${JSON.stringify(filter)}`);
  if (!lines.data) return <Skeleton className="h-10 rounded-lg" />;
  return (
    <ul className="space-y-1 border-t pt-2 text-sm" aria-label={t("purchases.details", { name: product.name })} data-testid="product-lines">
      {lines.data.map((line, index) => (
        <li key={`${line.receipt_id}:${index}`} className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
          <span className="tabular w-28 shrink-0 text-muted-foreground">{shortDate(line.purchased_on, locale)}</span>
          <span className="min-w-0 flex-1 truncate">{line.store_name || "–"}</span>
          <span className="tabular text-muted-foreground">{amount(line.quantity, line.unit, locale, t)}</span>
          <span className="tabular w-20 text-right">{money(line.total_cents, locale)}</span>
          <Link href={`/receipts/${line.receipt_id}`} className="text-primary" aria-label={`${t("purchases.openReceipt")} #${line.receipt_id}`}>
            <ExternalLink className="size-4" />
          </Link>
        </li>
      ))}
    </ul>
  );
}

function ProductRow({ product, color, filter }: { product: Product; color: string; filter: PurchaseFilter }) {
  const { t, locale } = useI18n();
  const [open, setOpen] = useState(false);
  return (
    <li className="rounded-xl bg-muted/40 px-3 py-2" data-testid="product-row">
      <button type="button" className="flex w-full min-w-0 items-start gap-3 text-left" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="mt-1.5 size-2.5 shrink-0 rounded-full" style={{ background: color }} aria-hidden />
        <span className="min-w-0 flex-1">
          <span className="block truncate font-medium">{product.name}</span>
          <span className="block text-xs text-muted-foreground">
            {[
              quantities(product, locale, t),
              t("purchases.average", { price: averages(product, locale, t) }),
              t("purchases.times", { count: product.lines }),
              t("purchases.last", { date: shortDate(product.last_bought, locale) }),
            ].join(" · ")}
          </span>
          {product.stores.length > 0 && <span className="block truncate text-xs text-muted-foreground">{product.stores.join(", ")}</span>}
        </span>
        <span className="tabular shrink-0 font-semibold">{money(product.total_cents, locale)}</span>
        <ChevronDown className={cn("mt-0.5 size-4 shrink-0 transition-transform", open && "rotate-180")} aria-hidden />
      </button>
      {open && (
        <div className="mt-2">
          <ProductLines product={product} filter={filter} />
        </div>
      )}
    </li>
  );
}

export function Purchases() {
  const { t, locale } = useI18n();
  const [filter, setFilter] = useState<PurchaseFilter>({
    range: "30d",
    custom: { start: "", end: "" },
    food: "all",
    store_id: null,
    category_id: null,
    q: "",
  });
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<Sort>("total");
  const stores = useData(() => api.stores(), "stores");
  const categoryList = useData(() => api.categories(), "categories");

  // the search asks the API once typing pauses
  useEffect(() => {
    const timer = setTimeout(() => setFilter((current) => (current.q === search ? current : { ...current, q: search })), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const ready = filter.range !== "custom" || validCustomRange(filter.custom.start, filter.custom.end);
  const data = useData(() => (ready ? api.purchases(filter) : Promise.resolve(null)), JSON.stringify(filter));
  const update = (changes: Partial<PurchaseFilter>) => setFilter({ ...filter, ...changes });
  const categories = categoryList.data ?? [];
  const colorOf = (id: number | null) => categories.find((c) => c.id === id)?.color ?? "#64748b";
  const p = data.data;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">{t("purchases.title")}</h1>
          <p className="text-sm text-muted-foreground">{t("purchases.hint")}</p>
        </div>
        <RangePicker value={filter.range} onChange={(range) => update({ range })} />
      </div>
      {filter.range === "custom" && <CustomRangeFields value={filter.custom} onChange={(custom) => update({ custom })} />}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {(
          [
            ["purchases.food", p?.food_cents],
            ["purchases.nonfood", p?.nonfood_cents],
            ["purchases.total", p?.total_cents],
          ] as const
        ).map(([label, cents], index) => (
          <Tile key={label} index={index} title={t(label)} testId={`purchases-${label.split(".")[1]}`}>
            {cents === undefined ? <Skeleton className="h-8 w-28" /> : <p className="tabular text-2xl font-semibold">{money(cents, locale)}</p>}
          </Tile>
        ))}
      </div>

      <div className="glass grid grid-cols-1 gap-3 rounded-2xl p-3 sm:grid-cols-2 lg:grid-cols-5" data-testid="purchases-filters">
        <div className="min-w-0 space-y-1 sm:col-span-2 lg:col-span-1">
          <Label htmlFor="purchase-search" className="text-xs">
            {t("purchases.search")}
          </Label>
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input id="purchase-search" type="search" value={search} maxLength={100} onChange={(e) => setSearch(e.target.value)} className="pl-8" />
          </div>
        </div>
        <div className="min-w-0 space-y-1">
          <Label htmlFor="purchase-kind" className="text-xs">
            {t("purchases.kind")}
          </Label>
          <select
            id="purchase-kind"
            value={filter.food}
            onChange={(e) => update({ food: e.target.value as PurchaseFilter["food"] })}
            className={SELECT_CLASS}
          >
            <option value="all">{t("purchases.all")}</option>
            <option value="food">{t("purchases.food")}</option>
            <option value="nonfood">{t("purchases.nonfood")}</option>
          </select>
        </div>
        <div className="min-w-0 space-y-1">
          <Label htmlFor="purchase-store" className="text-xs">
            {t("purchases.store")}
          </Label>
          <select
            id="purchase-store"
            value={filter.store_id ?? ""}
            onChange={(e) => update({ store_id: e.target.value ? Number(e.target.value) : null })}
            className={SELECT_CLASS}
          >
            <option value="">{t("purchases.allStores")}</option>
            {byName(stores.data ?? [], (s) => s.name, locale).map((store) => (
              <option key={store.id} value={store.id}>
                {store.name}
              </option>
            ))}
          </select>
        </div>
        <div className="min-w-0 space-y-1">
          <Label htmlFor="purchase-category" className="text-xs">
            {t("purchases.category")}
          </Label>
          <select
            id="purchase-category"
            value={filter.category_id ?? ""}
            onChange={(e) => update({ category_id: e.target.value ? Number(e.target.value) : null })}
            className={SELECT_CLASS}
          >
            <option value="">{t("purchases.allCategories")}</option>
            {byName(spendingCategories(categories), (c) => (locale === "de" ? c.name_de : c.name_en), locale).map((c) => (
              <option key={c.id} value={c.id}>
                {locale === "de" ? c.name_de : c.name_en}
              </option>
            ))}
          </select>
        </div>
        <div className="min-w-0 space-y-1">
          <Label htmlFor="purchase-sort" className="text-xs">
            {t("purchases.sort")}
          </Label>
          <select id="purchase-sort" value={sort} onChange={(e) => setSort(e.target.value as Sort)} className={SELECT_CLASS}>
            {SORTS.map((option) => (
              <option key={option.value} value={option.value}>
                {t(option.label)}
              </option>
            ))}
          </select>
        </div>
      </div>

      {!ready ? (
        <p className="glass rounded-2xl p-6 text-center text-muted-foreground">{t("range.incomplete")}</p>
      ) : data.error ? (
        <p className="glass rounded-2xl p-6 text-destructive">{data.error.message}</p>
      ) : !p ? (
        <Skeleton className="h-48 rounded-2xl" />
      ) : (
        <Tile index={3} title={t("purchases.count", { count: p.products.length })} testId="products">
          {p.products.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("purchases.empty")}</p>
          ) : (
            <ul className="space-y-1.5">
              {sorted(p.products, sort, locale).map((product) => (
                <ProductRow key={product.key} product={product} color={colorOf(product.category_id)} filter={filter} />
              ))}
            </ul>
          )}
        </Tile>
      )}
    </div>
  );
}
