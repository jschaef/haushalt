"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowDownRight, ArrowUpRight, ChevronDown, ExternalLink, Search } from "lucide-react";
import { Tile } from "@/components/bento";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type Category, type CustomRange, type PriceChange, type PriceFilter, type Range, type Store, type Unit } from "@/lib/api";
import { money, shortDate } from "@/lib/format";
import { useData } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n/provider";
import { byName } from "@/lib/sort";
import { cn } from "@/lib/utils";

// Price changes (Jochen, 2026-11-16): the same article in the same store
// against its previous purchase, price per unit before the discount.

const SELECT_CLASS =
  "h-9 w-full min-w-0 rounded-lg border border-input bg-transparent px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50 dark:bg-input/30";

function PriceRow({ change, color }: { change: PriceChange; color: string }) {
  const { t, locale } = useI18n();
  const [open, setOpen] = useState(false);
  const up = change.diff_cents > 0;
  const perUnit = (cents: number, unit: Unit) => `${money(cents, locale)}/${t(`unit.${unit}`)}`;
  const Arrow = up ? ArrowUpRight : ArrowDownRight;
  return (
    <li className="rounded-xl bg-muted/40 px-3 py-2" data-testid="price-row">
      <button type="button" className="flex w-full min-w-0 items-start gap-3 text-left" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="mt-1.5 size-2.5 shrink-0 rounded-full" style={{ background: color }} aria-hidden />
        <span className="min-w-0 flex-1">
          <span className="block font-medium break-words">{change.name}</span>
          <span className="block text-xs break-words text-muted-foreground">
            {[
              change.store_name,
              t("prices.from", { price: perUnit(change.old_cents, change.unit), date: shortDate(change.previous_on, locale) }),
              t("prices.since", { date: shortDate(change.changed_on, locale) }),
            ].join(" · ")}
          </span>
        </span>
        <span className="shrink-0 text-right">
          <span className="tabular block font-semibold">{perUnit(change.new_cents, change.unit)}</span>
          {/* the direction is in the text too, not only in the color (WCAG 1.4.1) */}
          <span className={cn("tabular inline-flex items-center gap-0.5 text-xs font-medium", up ? "text-destructive" : "text-primary")}>
            <Arrow className="size-3.5" aria-hidden />
            {up ? "+" : "−"}
            {money(Math.abs(change.diff_cents), locale)} ({up ? "+" : "−"}
            {Math.abs(change.pct).toLocaleString(locale === "de" ? "de-DE" : "en-GB")} %)
            <span className="sr-only"> {t(up ? "prices.up" : "prices.down")}</span>
          </span>
        </span>
        <ChevronDown className={cn("mt-0.5 size-4 shrink-0 transition-transform", open && "rotate-180")} aria-hidden />
      </button>
      {open && (
        <ul className="mt-2 space-y-1 border-t pt-2 text-sm" aria-label={t("prices.history", { name: change.name })} data-testid="price-history">
          {change.history.map((point, index) => (
            <li key={`${point.receipt_id}:${index}`} className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
              <span className="tabular w-28 shrink-0 text-muted-foreground">{shortDate(point.date, locale)}</span>
              <span className="tabular min-w-0 flex-1">{perUnit(point.unit_cents, change.unit)}</span>
              {point.discount_cents > 0 && (
                <span className="text-xs text-muted-foreground">{t("prices.discount", { amount: money(point.discount_cents, locale) })}</span>
              )}
              <Link href={`/receipts/${point.receipt_id}`} className="text-primary" aria-label={`${t("purchases.openReceipt")} #${point.receipt_id}`}>
                <ExternalLink className="size-4" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

export function PriceChanges({
  range,
  custom,
  ready,
  stores,
  categories,
}: {
  range: Range;
  custom: CustomRange;
  ready: boolean;
  stores: Store[];
  categories: Category[];
}) {
  const { t, locale } = useI18n();
  const [filter, setFilter] = useState<PriceFilter>({ food: "all", store_id: null, direction: "all", min_pct: 0, q: "" });
  const [search, setSearch] = useState("");
  const [minPct, setMinPct] = useState("");

  // typed fields ask the API once typing pauses
  useEffect(() => {
    const pct = Number(minPct.replace(",", "."));
    const min_pct = Number.isFinite(pct) && pct > 0 ? Math.min(pct, 1000) : 0;
    const timer = setTimeout(
      () => setFilter((current) => (current.q === search && current.min_pct === min_pct ? current : { ...current, q: search, min_pct })),
      300,
    );
    return () => clearTimeout(timer);
  }, [search, minPct]);

  const key = `${range}:${JSON.stringify(custom)}:${JSON.stringify(filter)}`;
  const data = useData(() => (ready ? api.priceChanges(range, custom, filter) : Promise.resolve(null)), key);
  const update = (changes: Partial<PriceFilter>) => setFilter({ ...filter, ...changes });
  const colorOf = (id: number | null) => categories.find((c) => c.id === id)?.color ?? "#64748b";
  const changes = data.data?.changes;

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("prices.hint")}</p>
      <div className="glass grid grid-cols-1 gap-3 rounded-2xl p-3 sm:grid-cols-2 lg:grid-cols-5" data-testid="price-filters">
        <div className="min-w-0 space-y-1 sm:col-span-2 lg:col-span-1">
          <Label htmlFor="price-search" className="text-xs">
            {t("purchases.search")}
          </Label>
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input id="price-search" type="search" value={search} maxLength={100} onChange={(e) => setSearch(e.target.value)} className="pl-8" />
          </div>
        </div>
        <div className="min-w-0 space-y-1">
          <Label htmlFor="price-kind" className="text-xs">
            {t("purchases.kind")}
          </Label>
          <select id="price-kind" value={filter.food} onChange={(e) => update({ food: e.target.value as PriceFilter["food"] })} className={SELECT_CLASS}>
            <option value="all">{t("purchases.all")}</option>
            <option value="food">{t("purchases.food")}</option>
            <option value="nonfood">{t("purchases.nonfood")}</option>
          </select>
        </div>
        <div className="min-w-0 space-y-1">
          <Label htmlFor="price-store" className="text-xs">
            {t("purchases.store")}
          </Label>
          <select
            id="price-store"
            value={filter.store_id ?? ""}
            onChange={(e) => update({ store_id: e.target.value ? Number(e.target.value) : null })}
            className={SELECT_CLASS}
          >
            <option value="">{t("purchases.allStores")}</option>
            {byName(stores, (s) => s.name, locale).map((store) => (
              <option key={store.id} value={store.id}>
                {store.name}
              </option>
            ))}
          </select>
        </div>
        <div className="min-w-0 space-y-1">
          <Label htmlFor="price-direction" className="text-xs">
            {t("prices.direction")}
          </Label>
          <select
            id="price-direction"
            value={filter.direction}
            onChange={(e) => update({ direction: e.target.value as PriceFilter["direction"] })}
            className={SELECT_CLASS}
          >
            <option value="all">{t("prices.all")}</option>
            <option value="up">{t("prices.up")}</option>
            <option value="down">{t("prices.down")}</option>
          </select>
        </div>
        <div className="min-w-0 space-y-1">
          <Label htmlFor="price-min" className="text-xs">
            {t("prices.minPct")}
          </Label>
          <Input id="price-min" inputMode="decimal" value={minPct} maxLength={6} onChange={(e) => setMinPct(e.target.value)} />
        </div>
      </div>

      {!ready ? (
        <p className="glass rounded-2xl p-6 text-center text-muted-foreground">{t("range.incomplete")}</p>
      ) : data.error ? (
        <p className="glass rounded-2xl p-6 text-destructive">{data.error.message}</p>
      ) : !changes ? (
        <Skeleton className="h-48 rounded-2xl" />
      ) : (
        <Tile index={0} title={t("prices.count", { count: changes.length })} testId="price-changes">
          {changes.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("prices.empty")}</p>
          ) : (
            <ul className="space-y-1.5">
              {changes.map((change) => (
                <PriceRow key={`${change.key}:${change.store_id}:${change.unit}`} change={change} color={colorOf(change.category_id)} />
              ))}
            </ul>
          )}
        </Tile>
      )}
    </div>
  );
}
