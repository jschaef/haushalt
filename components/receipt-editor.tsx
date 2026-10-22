"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, ViewTransition } from "react";
import { AlertTriangle, ArrowLeft, Check, ExternalLink, Plus, RefreshCw, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { Tile } from "@/components/bento";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type Category, type Item, type Receipt } from "@/lib/api";
import { centsToInput, money, parseMoney } from "@/lib/format";
import { haptic, useData } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n/provider";
import type { Locale } from "@/lib/i18n/messages";
import { cn } from "@/lib/utils";

type Row = { key: string; id: number | null; name: string; quantity: string; amount: string; category_id: number | null; unit_price_cents: number | null };

type Draft = { store_name: string; purchased_on: string; total: string; rows: Row[] };

let nextKey = 0;
const MAX_DUPLICATE_LINKS = 5;

function toDraft(receipt: Receipt, locale: Locale): Draft {
  return {
    store_name: receipt.store_name,
    purchased_on: receipt.purchased_on ?? "",
    total: centsToInput(receipt.total_cents, locale),
    rows: receipt.items.map((item) => ({
      key: `r${nextKey++}`,
      id: item.id ?? null,
      name: item.name,
      quantity: String(item.quantity),
      amount: centsToInput(item.total_cents, locale),
      category_id: item.category_id,
      unit_price_cents: item.unit_price_cents,
    })),
  };
}

// null when a field does not parse; the editor shows which one
function toPatch(draft: Draft) {
  const total = parseMoney(draft.total);
  const items: Item[] = [];
  for (const row of draft.rows) {
    const cents = parseMoney(row.amount);
    const quantity = Number(row.quantity.replace(",", "."));
    if (cents === null || !row.name.trim() || !Number.isFinite(quantity)) return null;
    items.push({ id: row.id, name: row.name.trim(), quantity, total_cents: cents, category_id: row.category_id, unit_price_cents: row.unit_price_cents });
  }
  if (total === null) return null;
  return { store_name: draft.store_name, purchased_on: draft.purchased_on || null, total_cents: total, items };
}

function CategorySelect({ value, categories, onChange }: { value: number | null; categories: Category[]; onChange: (id: number | null) => void }) {
  const { t, locale } = useI18n();
  const current = categories.find((c) => c.id === value);
  return (
    <div className="relative flex items-center">
      <span className="pointer-events-none absolute left-2 size-2.5 rounded-full" style={{ background: current?.color ?? "transparent" }} />
      <select
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value ? Number(event.target.value) : null)}
        className="h-8 w-full appearance-none rounded-lg border border-input bg-transparent pl-6 pr-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50 dark:bg-input/30"
        aria-label={t("receipt.category")}
      >
        <option value="">{t("receipt.uncategorized")}</option>
        {categories.map((c) => (
          <option key={c.id} value={c.id}>
            {locale === "de" ? c.name_de : c.name_en}
          </option>
        ))}
      </select>
    </div>
  );
}

export function ReceiptEditor({ id }: { id: number }) {
  const { t, locale } = useI18n();
  const router = useRouter();
  const receipt = useData(() => api.receipt(id), `receipt:${id}`);
  const categories = useData(() => api.categories(), "categories");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- editable copy of the loaded receipt
    if (receipt.data) setDraft(toDraft(receipt.data, locale));
  }, [receipt.data, locale]);

  const patch = useMemo(() => (draft ? toPatch(draft) : null), [draft]);
  const itemSum = patch?.items.reduce((sum, item) => sum + item.total_cents, 0) ?? 0;
  const mismatch = patch && patch.items.length > 0 && itemSum !== patch.total_cents;

  if (receipt.error) return <p className="glass rounded-2xl p-6 text-destructive">{receipt.error.message}</p>;
  if (!receipt.data || !draft || !categories.data) return <Skeleton className="h-96 rounded-3xl" />;
  const r = receipt.data;

  const update = (changes: Partial<Draft>) => setDraft({ ...draft, ...changes });
  const updateRow = (key: string, changes: Partial<Row>) =>
    update({ rows: draft.rows.map((row) => (row.key === key ? { ...row, ...changes } : row)) });

  async function save(confirm: boolean) {
    if (!patch) return;
    setBusy(true);
    try {
      let saved = await api.updateReceipt(id, patch);
      if (confirm) {
        saved = await api.confirmReceipt(id);
        haptic([10, 30, 10]);
        toast.success(t("receipt.confirmed"));
        router.push("/receipts?status=draft");
        return;
      }
      receipt.setData(saved);
      toast.success(t("receipt.saved"));
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function reread() {
    setBusy(true);
    try {
      receipt.setData(await api.rereadReceipt(id));
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!window.confirm(t("receipt.deleteAsk"))) return;
    await api.deleteReceipt(id);
    toast.success(t("receipts.deleted"));
    router.push("/receipts");
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={() => router.back()}>
          <ArrowLeft /> {t("receipt.back")}
        </Button>
        <span className="ml-auto text-xs text-muted-foreground">#{r.id}</span>
      </div>

      {r.error && (
        <div role="alert" className="glass flex items-center gap-2 rounded-2xl border-destructive/40 p-3 text-sm text-destructive">
          <AlertTriangle className="size-4 shrink-0" />
          {r.error === "not_a_receipt" ? t("receipt.notReceipt") : t("receipt.readError", { error: r.error })}
        </div>
      )}
      {r.duplicates.length > 0 && (
        <div role="status" className="glass flex items-center gap-2 rounded-2xl p-3 text-sm text-chart-3">
          <AlertTriangle className="size-4 shrink-0" />
          <span className="flex-1">{t("receipt.duplicate", { count: r.duplicates.length })}</span>
          <span className="flex flex-wrap gap-2">
            {r.duplicates.slice(0, MAX_DUPLICATE_LINKS).map((dup) => (
              <Link key={dup} href={`/receipts/${dup}`} className="underline">
                #{dup}
              </Link>
            ))}
            {r.duplicates.length > MAX_DUPLICATE_LINKS && <span>…</span>}
          </span>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,22rem)_1fr]">
        <Tile className="lg:sticky lg:top-24 lg:self-start" index={0}>
          {r.source === "pdf" ? (
            <a href={api.fileUrl(r.id)} target="_blank" rel="noopener" className="flex items-center gap-2 text-sm text-primary">
              <ExternalLink className="size-4" /> {t("receipt.openFile")}
            </a>
          ) : (
            <a href={api.fileUrl(r.id)} target="_blank" rel="noopener">
              {/* eslint-disable-next-line @next/next/no-img-element -- authenticated API image */}
              <img src={api.fileUrl(r.id)} alt={r.file_name} className="max-h-[70vh] w-full rounded-xl object-contain" />
            </a>
          )}
        </Tile>

        <div className="space-y-4">
          <ViewTransition name={`receipt-${r.id}`} share="morph">
            <Tile index={1} className="grid gap-3 sm:grid-cols-3">
              <div className="space-y-1.5">
                <Label htmlFor="store">{t("receipt.store")}</Label>
                <Input id="store" value={draft.store_name} onChange={(e) => update({ store_name: e.target.value })} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="date">{t("receipt.date")}</Label>
                <Input id="date" type="date" value={draft.purchased_on} onChange={(e) => update({ purchased_on: e.target.value })} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="total">{t("receipt.total")}</Label>
                <Input
                  id="total"
                  inputMode="decimal"
                  value={draft.total}
                  aria-invalid={parseMoney(draft.total) === null}
                  onChange={(e) => update({ total: e.target.value })}
                  className="tabular text-right font-semibold"
                />
              </div>
            </Tile>
          </ViewTransition>

          <Tile index={2} title={`${t("receipt.items")} (${draft.rows.length})`}>
            <ul className="space-y-2" data-testid="items">
              {draft.rows.map((row) => (
                <li key={row.key} className="grid grid-cols-[1fr_5.5rem_auto] items-center gap-2 rounded-xl bg-muted/40 p-2 sm:grid-cols-[1fr_4rem_6rem_11rem_auto]">
                  <Input value={row.name} aria-label={t("receipt.item")} onChange={(e) => updateRow(row.key, { name: e.target.value })} className="col-span-2 sm:col-span-1" />
                  <Input
                    value={row.quantity}
                    inputMode="decimal"
                    aria-label={t("receipt.quantity")}
                    onChange={(e) => updateRow(row.key, { quantity: e.target.value })}
                    className="tabular hidden text-right sm:block"
                  />
                  <Input
                    value={row.amount}
                    inputMode="decimal"
                    aria-label={t("receipt.amount")}
                    aria-invalid={parseMoney(row.amount) === null}
                    onChange={(e) => updateRow(row.key, { amount: e.target.value })}
                    className="tabular text-right"
                  />
                  <div className="col-span-2 sm:col-span-1">
                    <CategorySelect value={row.category_id} categories={categories.data!} onChange={(category_id) => updateRow(row.key, { category_id })} />
                  </div>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={t("common.delete")}
                    onClick={() => update({ rows: draft.rows.filter((x) => x.key !== row.key) })}
                  >
                    <X />
                  </Button>
                </li>
              ))}
            </ul>
            <Button
              variant="outline"
              size="sm"
              className="self-start"
              onClick={() =>
                update({
                  rows: [...draft.rows, { key: `r${nextKey++}`, id: null, name: "", quantity: "1", amount: "", category_id: null, unit_price_cents: null }],
                })
              }
            >
              <Plus /> {t("receipt.addItem")}
            </Button>
            {mismatch && (
              <p className={cn("flex items-center gap-2 text-sm text-chart-3")} data-testid="mismatch">
                <AlertTriangle className="size-4" />
                {t("receipt.mismatch", { sum: money(itemSum, locale), total: money(patch!.total_cents, locale) })}
              </p>
            )}
          </Tile>

          <div className="glass sticky bottom-24 z-10 flex bg-background/90 flex-wrap gap-2 rounded-2xl p-3 md:bottom-4">
            <Button onClick={() => save(true)} disabled={busy || !patch || !draft.purchased_on} className="bg-gradient-to-r from-primary to-chart-4">
              <Check /> {t("receipt.confirm")}
            </Button>
            <Button variant="outline" onClick={() => save(false)} disabled={busy || !patch}>
              {t("receipt.save")}
            </Button>
            <Button variant="ghost" onClick={reread} disabled={busy}>
              <RefreshCw /> {t("receipt.reread")}
            </Button>
            <Button variant="destructive" onClick={remove} disabled={busy} className="ml-auto">
              <Trash2 /> {t("receipt.delete")}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
