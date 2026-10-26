"use client";

import { useId, useMemo, useState, type FormEvent } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Tile } from "@/components/bento";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { TagChips, TagFilter, TagPicker } from "@/components/tags";
import { api, spendingCategories, type Category, type Recurring, type RecurringBody, type Tag } from "@/lib/api";
import { centsToInput, money, parseMoney, shortDate } from "@/lib/format";
import { useData } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n/provider";
import { byName } from "@/lib/sort";
import type { Locale, MessageKey } from "@/lib/i18n/messages";

type Body = RecurringBody;

const INTERVALS: { months: number; label: MessageKey }[] = [
  { months: 1, label: "fixed.monthly" },
  { months: 3, label: "fixed.quarterly" },
  { months: 6, label: "fixed.halfYearly" },
  { months: 12, label: "fixed.yearly" },
];

const SELECT_CLASS =
  "h-8 w-full appearance-none rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50 dark:bg-input/30";

function today(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

function intervalLabel(months: number, t: (key: MessageKey) => string): string {
  const known = INTERVALS.find((i) => i.months === months);
  return known ? t(known.label) : `${months} ×`;
}

function CostForm({
  initial,
  categories,
  tags,
  onTagCreated,
  locale,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial?: Recurring;
  categories: Category[];
  tags: Tag[];
  onTagCreated: (tag: Tag) => void;
  locale: Locale;
  submitLabel: string;
  onSubmit: (body: Body) => Promise<boolean>;
  onCancel?: () => void;
}) {
  const { t } = useI18n();
  const uid = useId();
  const sorted = useMemo(() => byName(spendingCategories(categories), (c) => (locale === "de" ? c.name_de : c.name_en), locale), [categories, locale]);
  const [name, setName] = useState(initial?.name ?? "");
  const [amount, setAmount] = useState(initial ? centsToInput(initial.amount_cents, locale) : "");
  const [categoryId, setCategoryId] = useState<number | null>(
    // a new cost starts in the first category of the fixed kind
    initial ? initial.category_id : ((sorted.find((c) => c.kind === "fixed") ?? sorted[0])?.id ?? null),
  );
  const [months, setMonths] = useState(initial?.interval_months ?? 1);
  const [start, setStart] = useState(initial?.start_on ?? today());
  const [end, setEnd] = useState(initial?.end_on ?? "");
  const [tagIds, setTagIds] = useState<number[]>(initial?.tag_ids ?? []);
  const [busy, setBusy] = useState(false);

  const cents = parseMoney(amount);
  const amountInvalid = cents === null;
  const endInvalid = end !== "" && start !== "" && end < start;
  const valid = name.trim() !== "" && !amountInvalid && start !== "" && !endInvalid;
  const intervals = INTERVALS.some((i) => i.months === months) ? INTERVALS : [...INTERVALS, { months, label: "fixed.monthly" as MessageKey }];

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!valid || cents === null) return;
    setBusy(true);
    try {
      const ok = await onSubmit({
        name: name.trim(),
        category_id: categoryId,
        amount_cents: cents,
        interval_months: months,
        start_on: start,
        end_on: end || null,
        // keep the link of a utility instalment to its meter
        meter_id: initial?.meter_id ?? null,
        tag_ids: tagIds,
      });
      if (ok && !initial) {
        setName("");
        setAmount("");
        setEnd("");
        setTagIds([]);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <div className="space-y-1.5">
        <Label htmlFor={`${uid}-name`}>{t("fixed.name")}</Label>
        <Input id={`${uid}-name`} value={name} onChange={(e) => setName(e.target.value)} required />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${uid}-amount`}>{t("fixed.amount")}</Label>
        <Input
          id={`${uid}-amount`}
          inputMode="decimal"
          value={amount}
          aria-invalid={amountInvalid}
          onChange={(e) => setAmount(e.target.value)}
          className="tabular text-right"
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${uid}-category`}>{t("receipt.category")}</Label>
        <select
          id={`${uid}-category`}
          value={categoryId ?? ""}
          onChange={(e) => setCategoryId(e.target.value ? Number(e.target.value) : null)}
          className={SELECT_CLASS}
        >
          <option value="">{t("receipt.uncategorized")}</option>
          {sorted.map((c) => (
            <option key={c.id} value={c.id}>
              {locale === "de" ? c.name_de : c.name_en}
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${uid}-interval`}>{t("fixed.interval")}</Label>
        <select id={`${uid}-interval`} value={months} onChange={(e) => setMonths(Number(e.target.value))} className={SELECT_CLASS}>
          {intervals.map((i) => (
            <option key={i.months} value={i.months}>
              {intervalLabel(i.months, t)}
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${uid}-start`}>{t("fixed.start")}</Label>
        <Input id={`${uid}-start`} type="date" value={start} onChange={(e) => setStart(e.target.value)} required />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${uid}-end`}>{t("fixed.end")}</Label>
        <Input id={`${uid}-end`} type="date" value={end} aria-invalid={endInvalid} onChange={(e) => setEnd(e.target.value)} />
      </div>
      <div className="sm:col-span-2 lg:col-span-3">
        <TagPicker tags={tags} selected={tagIds} onChange={setTagIds} onCreated={onTagCreated} />
      </div>
      <div className="flex flex-wrap gap-2 sm:col-span-2 lg:col-span-3">
        <Button type="submit" disabled={busy || !valid}>
          {!initial && <Plus />} {submitLabel}
        </Button>
        {onCancel && (
          <Button type="button" variant="ghost" onClick={onCancel}>
            {t("common.cancel")}
          </Button>
        )}
      </div>
    </form>
  );
}

export function FixedCosts() {
  const { t, locale } = useI18n();
  const costs = useData(() => api.recurring(), "recurring");
  const categories = useData(() => api.categories(), "categories");
  const tagList = useData(() => api.tags(), "tags");
  const [editing, setEditing] = useState<number | null>(null);
  const [filter, setFilter] = useState<number | null>(null);

  if (costs.error) return <p className="glass rounded-2xl p-6 text-destructive">{costs.error.message}</p>;
  if (!costs.data || !categories.data || !tagList.data) return <Skeleton className="h-96 rounded-3xl" />;
  const cats = categories.data;
  const tags = tagList.data;
  const addTag = (tag: Tag) => tagList.setData([...tags, tag].sort((a, b) => a.name.localeCompare(b.name)));
  const shown = filter === null ? costs.data : costs.data.filter((c) => c.tag_ids.includes(filter));
  const monthly = costs.data
    .filter((c) => !c.end_on || c.end_on >= today())
    .filter((c) => c.start_on <= today())
    .reduce((sum, c) => sum + c.daily_cents * (365.25 / 12), 0);

  async function run(action: () => Promise<unknown>): Promise<boolean> {
    try {
      await action();
      toast.success(t("receipt.saved"));
      await costs.reload();
      return true;
    } catch (error) {
      toast.error((error as Error).message);
      return false;
    }
  }

  async function remove(cost: Recurring) {
    if (!window.confirm(`${t("common.delete")}: ${cost.name}?`)) return;
    try {
      await api.deleteRecurring(cost.id);
      toast.success(t("common.delete"));
      await costs.reload();
    } catch (error) {
      toast.error((error as Error).message);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t("fixed.title")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("fixed.hint")}</p>
      </div>

      <Tile index={0} title={t("fixed.sumMonthly")}>
        <p className="tabular text-3xl font-semibold" data-testid="fixed-sum">
          {money(Math.round(monthly), locale)}
        </p>
      </Tile>

      <Tile index={1} title={t("fixed.add")}>
        <CostForm
          categories={cats}
          tags={tags}
          onTagCreated={addTag}
          locale={locale}
          submitLabel={t("common.add")}
          onSubmit={(body) => run(() => api.createRecurring(body))}
        />
      </Tile>

      <TagFilter tags={tags} value={filter} onChange={setFilter} />

      {costs.data.length === 0 ? (
        <p className="glass rounded-2xl p-6 text-center text-sm text-muted-foreground">{t("fixed.empty")}</p>
      ) : (
        <ul className="space-y-2">
          {shown.map((cost) => {
            const category = cats.find((c) => c.id === cost.category_id);
            if (editing === cost.id) {
              return (
                <li key={cost.id} data-testid="recurring-row" className="glass rounded-2xl p-4">
                  <CostForm
                    initial={cost}
                    categories={cats}
                    tags={tags}
                    onTagCreated={addTag}
                    locale={locale}
                    submitLabel={t("common.save")}
                    onCancel={() => setEditing(null)}
                    onSubmit={async (body) => {
                      const ok = await run(() => api.updateRecurring(cost.id, body));
                      if (ok) setEditing(null);
                      return ok;
                    }}
                  />
                </li>
              );
            }
            return (
              <li key={cost.id} data-testid="recurring-row" className="glass flex flex-wrap items-center gap-x-4 gap-y-2 rounded-2xl p-4">
                <div className="min-w-0 flex-1 basis-48">
                  <p className="truncate font-medium">{cost.name}</p>
                  <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <span className="size-2.5 shrink-0 rounded-full" style={{ background: category?.color ?? "transparent" }} aria-hidden />
                    {category ? (locale === "de" ? category.name_de : category.name_en) : t("receipt.uncategorized")}
                  </p>
                  <TagChips ids={cost.tag_ids} tags={tags} />
                </div>
                <div className="text-right">
                  <p className="tabular font-semibold">
                    {money(cost.amount_cents, locale)} <span className="text-xs font-normal text-muted-foreground">{intervalLabel(cost.interval_months, t)}</span>
                  </p>
                  <p className="tabular text-xs text-muted-foreground">{t("fixed.perDay", { amount: money(cost.daily_cents, locale) })}</p>
                </div>
                <p className="w-full text-xs text-muted-foreground sm:w-auto">
                  {shortDate(cost.start_on, locale)}
                  {cost.end_on ? ` – ${shortDate(cost.end_on, locale)}` : ""}
                </p>
                <div className="ml-auto flex gap-1">
                  <Button variant="ghost" size="icon-sm" aria-label={t("common.edit")} onClick={() => setEditing(cost.id)}>
                    <Pencil />
                  </Button>
                  <Button variant="ghost" size="icon-sm" aria-label={t("common.delete")} onClick={() => remove(cost)}>
                    <Trash2 />
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
