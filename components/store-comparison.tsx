"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Search, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Tile } from "@/components/bento";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type Category, type CompareFilter, type CustomRange, type Range, type StoreComparison as Comparison } from "@/lib/api";
import { money, shortDate } from "@/lib/format";
import { useData } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";

// Store comparison (Jochen, 2026-11-16): the same product in several shops,
// matched by the comparison name the model gives every receipt line; per shop
// the latest price per unit before the discount.

const SELECT_CLASS =
  "h-9 w-full min-w-0 rounded-lg border border-input bg-transparent px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50 dark:bg-input/30";

function ComparisonRow({ product, color }: { product: Comparison; color: string }) {
  const { t, locale } = useI18n();
  const pct = product.spread_pct.toLocaleString(locale === "de" ? "de-DE" : "en-GB");
  return (
    <li className="rounded-xl bg-muted/40 px-3 py-2" data-testid="compare-row">
      <div className="flex min-w-0 items-start gap-3">
        <span className="mt-1.5 size-2.5 shrink-0 rounded-full" style={{ background: color }} aria-hidden />
        <span className="min-w-0 flex-1">
          <span className="block font-medium break-words">{product.name}</span>
          <span className="block text-xs text-muted-foreground">
            {t("compare.spread", { amount: money(product.spread_cents, locale), pct })}
          </span>
        </span>
      </div>
      <ul className="mt-2 space-y-1 border-t pt-2 text-sm" aria-label={t("compare.stores", { name: product.name })}>
        {product.stores.map((store, index) => (
          <li key={store.store_id} className="flex flex-wrap items-center gap-x-3 gap-y-0.5" data-testid="compare-store">
            <span className={cn("min-w-0 flex-1 break-words", index === 0 && "font-semibold")}>
              {store.store_name}
              {index === 0 && <span className="ml-2 rounded-full border px-2 py-0.5 text-xs font-medium">{t("compare.cheapest")}</span>}
            </span>
            <span className="tabular font-medium">
              {money(store.unit_cents, locale)}/{t(`unit.${product.unit}`)}
            </span>
            <span className="w-full text-xs break-words text-muted-foreground sm:w-auto">
              {[shortDate(store.date, locale), t("compare.article", { name: store.article })].join(" · ")}
              {store.discount_cents > 0 && ` · ${t("prices.discount", { amount: money(store.discount_cents, locale) })}`}
            </span>
            <Link href={`/receipts/${store.receipt_id}`} className="text-xs text-primary underline-offset-4 hover:underline">
              {t("purchases.openReceipt")}
              <span className="sr-only"> {store.store_name}</span>
            </Link>
          </li>
        ))}
      </ul>
    </li>
  );
}

export function StoreComparison({
  range,
  custom,
  ready,
  categories,
}: {
  range: Range;
  custom: CustomRange;
  ready: boolean;
  categories: Category[];
}) {
  const { t } = useI18n();
  const [filter, setFilter] = useState<CompareFilter>({ food: "all", q: "" });
  const [search, setSearch] = useState("");
  const [naming, setNaming] = useState<number | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => setFilter((current) => (current.q === search ? current : { ...current, q: search })), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const key = `${range}:${JSON.stringify(custom)}:${JSON.stringify(filter)}`;
  const data = useData(() => (ready ? api.compareStores(range, custom, filter) : Promise.resolve(null)), key);
  const colorOf = (id: number | null) => categories.find((c) => c.id === id)?.color ?? "#64748b";
  const result = data.data;

  // one model request per batch of older article texts, until none remain
  async function nameOlder() {
    try {
      let remaining = result?.unnamed ?? 0;
      setNaming(remaining);
      while (remaining > 0) {
        const step = await api.nameOlderItems();
        if (step.named === 0) break;
        remaining = step.remaining;
        setNaming(remaining);
      }
      toast.success(t("compare.named"));
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setNaming(null);
      void data.reload();
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("compare.hint")}</p>
      <div className="glass grid grid-cols-1 gap-3 rounded-2xl p-3 sm:grid-cols-2" data-testid="compare-filters">
        <div className="min-w-0 space-y-1">
          <Label htmlFor="compare-search" className="text-xs">
            {t("purchases.search")}
          </Label>
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input id="compare-search" type="search" value={search} maxLength={100} onChange={(e) => setSearch(e.target.value)} className="pl-8" />
          </div>
        </div>
        <div className="min-w-0 space-y-1">
          <Label htmlFor="compare-kind" className="text-xs">
            {t("purchases.kind")}
          </Label>
          <select
            id="compare-kind"
            value={filter.food}
            onChange={(e) => setFilter({ ...filter, food: e.target.value as CompareFilter["food"] })}
            className={SELECT_CLASS}
          >
            <option value="all">{t("purchases.all")}</option>
            <option value="food">{t("purchases.food")}</option>
            <option value="nonfood">{t("purchases.nonfood")}</option>
          </select>
        </div>
      </div>

      {result && result.unnamed > 0 && (
        <div className="glass flex flex-wrap items-center gap-3 rounded-2xl p-3 text-sm" data-testid="compare-unnamed">
          <p className="min-w-0 flex-1">{t("compare.unnamed", { count: result.unnamed })}</p>
          <Button size="sm" onClick={nameOlder} disabled={naming !== null} aria-live="polite">
            <Sparkles aria-hidden />
            {naming !== null ? t("compare.naming", { count: naming }) : t("compare.name")}
          </Button>
        </div>
      )}

      {!ready ? (
        <p className="glass rounded-2xl p-6 text-center text-muted-foreground">{t("range.incomplete")}</p>
      ) : data.error ? (
        <p className="glass rounded-2xl p-6 text-destructive">{data.error.message}</p>
      ) : !result ? (
        <Skeleton className="h-48 rounded-2xl" />
      ) : (
        <Tile index={0} title={t("compare.count", { count: result.products.length })} testId="store-comparison">
          {result.products.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("compare.empty")}</p>
          ) : (
            <ul className="space-y-1.5">
              {result.products.map((product) => (
                <ComparisonRow key={`${product.key}:${product.unit}`} product={product} color={colorOf(product.category_id)} />
              ))}
            </ul>
          )}
        </Tile>
      )}
    </div>
  );
}
