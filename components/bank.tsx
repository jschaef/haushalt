"use client";

import Link from "next/link";
import { useId, useRef, useState, type ChangeEvent } from "react";
import { ChevronDown, ExternalLink, RefreshCw, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";
import { Tile } from "@/components/bento";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { TagChips, TagFilter, TagPicker } from "@/components/tags";
import { api, type BankTransaction, type BookingDecision, type BookingStatus, type Category, type ReceiptCandidate, type Recurring, type Tag } from "@/lib/api";
import { money, shortDate } from "@/lib/format";
import { useData } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n/provider";
import { byName } from "@/lib/sort";
import type { Locale, MessageKey } from "@/lib/i18n/messages";
import { cn } from "@/lib/utils";

// min-w-0: a select is otherwise as wide as its longest option and pushes
// the button next to it off narrow screens
const SELECT_CLASS =
  "h-8 w-full min-w-0 appearance-none rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50 dark:bg-input/30";

type Filter = BookingStatus | "all";
const FILTERS: Filter[] = ["review", "receipt", "fixed", "counted", "ignored", "all"];

const BADGE_CLASS: Record<BookingStatus, string> = {
  review: "bg-chart-3/20 text-chart-3",
  receipt: "bg-primary/15 text-primary",
  fixed: "bg-chart-2/20 text-chart-2",
  counted: "bg-positive/15 text-positive",
  ignored: "bg-muted text-muted-foreground",
};

const categoryName = (c: Category, locale: Locale) => (locale === "de" ? c.name_de : c.name_en);

type TagProps = { tags: Tag[]; onTagCreated: (tag: Tag) => void };

function DecisionPanel({
  booking,
  categories,
  recurring,
  tags,
  onTagCreated,
  onDecide,
  onDelete,
}: {
  booking: BankTransaction;
  categories: Category[];
  recurring: Recurring[];
  onDecide: (decision: BookingDecision) => Promise<void>;
  onDelete: () => void;
} & TagProps) {
  const { t, locale } = useI18n();
  const uid = useId();
  const candidates = useData<ReceiptCandidate[]>(() => api.candidates(booking.id), `candidates:${booking.id}`);
  const [recurringId, setRecurringId] = useState<string>(booking.recurring_id ? String(booking.recurring_id) : "");
  const [categoryId, setCategoryId] = useState<string>(booking.category_id ? String(booking.category_id) : "");
  const [tagIds, setTagIds] = useState<number[]>(booking.tag_ids);
  const [busy, setBusy] = useState(false);

  async function decide(decision: BookingDecision) {
    setBusy(true);
    try {
      await onDecide(decision);
    } finally {
      setBusy(false);
    }
  }

  return (
    // grid-cols-1: without it the single column on phones is as wide as its
    // widest content (a long tag or category name) and runs off the screen
    <div className="mt-3 grid grid-cols-1 gap-4 border-t border-border/60 pt-3 md:grid-cols-2" data-testid="booking-panel">
      <section className="space-y-2">
        <h3 className="text-sm font-medium">{t("bank.belongsToReceipt")}</h3>
        {candidates.loading && !candidates.data ? (
          <Skeleton className="h-10 rounded-xl" />
        ) : candidates.data && candidates.data.length > 0 ? (
          <ul className="space-y-1.5">
            {candidates.data.map((c) => (
              <li key={c.id} className="flex items-center gap-2 rounded-xl bg-muted/40 px-3 py-2 text-sm" data-testid="candidate">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="truncate font-medium">{c.store_name || t("receipts.unknownStore")}</span>
                    {c.store_matches && <Badge variant="secondary">{t("bank.storeMatches")}</Badge>}
                  </div>
                  <div className="tabular text-xs text-muted-foreground">
                    {c.purchased_on ? shortDate(c.purchased_on, locale) : t("receipts.noDate")} · {money(c.total_cents, locale)}
                  </div>
                </div>
                <Button size="sm" variant="outline" disabled={busy} onClick={() => decide({ status: "receipt", receipt_id: c.id })}>
                  {t("bank.choose")}
                </Button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">{candidates.error ? candidates.error.message : t("bank.noCandidates")}</p>
        )}
      </section>

      <section className="space-y-2">
        <Label htmlFor={`${uid}-fixed`}>{t("bank.fixedCost")}</Label>
        {recurring.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("bank.noFixed")}</p>
        ) : (
          <div className="flex gap-2">
            <select id={`${uid}-fixed`} value={recurringId} onChange={(e) => setRecurringId(e.target.value)} className={SELECT_CLASS}>
              <option value="">–</option>
              {byName(recurring, (r) => r.name, locale).map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
            <Button size="sm" variant="outline" disabled={busy || !recurringId} onClick={() => decide({ status: "fixed", recurring_id: Number(recurringId) })}>
              {t("bank.assign")}
            </Button>
          </div>
        )}
      </section>

      <section className="space-y-2">
        <Label htmlFor={`${uid}-category`}>{t("bank.countsItself")}</Label>
        <div className="flex gap-2">
          <select id={`${uid}-category`} value={categoryId} onChange={(e) => setCategoryId(e.target.value)} className={SELECT_CLASS}>
            <option value="">{t("receipt.uncategorized")}</option>
            {byName(categories, (c) => categoryName(c, locale), locale).map((c) => (
              <option key={c.id} value={c.id}>
                {categoryName(c, locale)}
              </option>
            ))}
          </select>
          <Button
            size="sm"
            variant="outline"
            disabled={busy || !categoryId}
            onClick={() => decide({ status: "counted", category_id: Number(categoryId), tag_ids: tagIds })}
          >
            {t("bank.assign")}
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">{t("bank.countsHint")}</p>
        <TagPicker tags={tags} selected={tagIds} onChange={setTagIds} onCreated={onTagCreated} />
      </section>

      <section className="flex flex-wrap items-end gap-2">
        {booking.status !== "ignored" && (
          <Button size="sm" variant="outline" disabled={busy} onClick={() => decide({ status: "ignored" })}>
            {t("bank.ignore")}
          </Button>
        )}
        {booking.status !== "review" && (
          <Button size="sm" variant="outline" disabled={busy} onClick={() => decide({ status: "review" })}>
            {t("bank.backToReview")}
          </Button>
        )}
        <Button size="sm" variant="ghost" className="ml-auto text-destructive" disabled={busy} onClick={onDelete}>
          <Trash2 /> {t("common.delete")}
        </Button>
      </section>
    </div>
  );
}

function BookingRow({
  booking,
  categories,
  recurring,
  tags,
  onTagCreated,
  onDecide,
  onDelete,
}: {
  booking: BankTransaction;
  categories: Category[];
  recurring: Recurring[];
  onDecide: (decision: BookingDecision) => Promise<void>;
  onDelete: () => void;
} & TagProps) {
  const { t, locale } = useI18n();
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const category = categories.find((c) => c.id === booking.category_id);
  const cost = recurring.find((r) => r.id === booking.recurring_id);

  return (
    <li className="glass rounded-2xl p-3" data-testid="booking-row">
      <div className="flex items-center gap-3">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          aria-label={t("bank.details")}
          onClick={() => setOpen((v) => !v)}
          className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-muted text-muted-foreground hover:bg-accent/40"
        >
          <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} />
        </button>
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium">{booking.counterparty || t("bank.noCounterparty")}</div>
          <div className="truncate text-xs text-muted-foreground">{booking.purpose || t("bank.noCounterparty")}</div>
          <div className="mt-0.5 text-xs text-muted-foreground">{shortDate(booking.booked_on, locale)}</div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className={cn("tabular font-semibold", booking.amount_cents < 0 ? "text-negative" : "text-positive")}>
            {money(booking.amount_cents, locale, booking.currency)}
          </span>
          <Badge className={BADGE_CLASS[booking.status]}>{t(`bank.${booking.status}`)}</Badge>
        </div>
      </div>
      {(booking.status === "receipt" || booking.status === "fixed" || booking.status === "counted") && (
        <div className="mt-2 pl-12 text-xs text-muted-foreground">
          {booking.status === "receipt" && booking.receipt_id !== null && (
            <Link href={`/receipts/${booking.receipt_id}`} className="inline-flex items-center gap-1 text-primary hover:underline">
              <ExternalLink className="size-3" /> {t("bank.openReceipt")}
            </Link>
          )}
          {booking.status === "fixed" && cost && <span>{cost.name}</span>}
          {booking.status === "counted" && category && (
            <span className="inline-flex items-center gap-1.5">
              <span className="size-2.5 rounded-full" style={{ background: category.color }} aria-hidden />
              {categoryName(category, locale)}
            </span>
          )}
          {/* a fixed booking shows the tags of its recurring cost */}
          <div className="mt-1">
            <TagChips ids={booking.status === "fixed" ? (cost?.tag_ids ?? []) : booking.tag_ids} tags={tags} />
          </div>
        </div>
      )}
      <div id={panelId}>
        {open && (
          <DecisionPanel
            booking={booking}
            categories={categories}
            recurring={recurring}
            tags={tags}
            onTagCreated={onTagCreated}
            onDecide={onDecide}
            onDelete={onDelete}
          />
        )}
      </div>
    </li>
  );
}

export function Bank() {
  const { t } = useI18n();
  const uid = useId();
  const input = useRef<HTMLInputElement>(null);
  const [filter, setFilter] = useState<Filter>("review");
  const [busy, setBusy] = useState(false);
  const bookings = useData(() => api.transactions(), "bank");
  const categories = useData(() => api.categories(), "categories");
  const recurring = useData(() => api.recurring(), "recurring");
  const tagList = useData(() => api.tags(), "tags");
  const [tagFilter, setTagFilter] = useState<number | null>(null);

  const all = bookings.data ?? [];
  const tags = tagList.data ?? [];
  const addTag = (tag: Tag) => tagList.setData([...tags, tag].sort((a, b) => a.name.localeCompare(b.name)));
  const tagsOf = (b: BankTransaction) => (b.status === "fixed" ? (recurring.data?.find((r) => r.id === b.recurring_id)?.tag_ids ?? []) : b.tag_ids);
  const count = (status: Filter) => (status === "all" ? all.length : all.filter((b) => b.status === status).length);
  const visible = all.filter((b) => (filter === "all" || b.status === filter) && (tagFilter === null || tagsOf(b).includes(tagFilter)));

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy(true);
    try {
      const r = await api.importStatement(file);
      toast.success(
        t("bank.imported", { imported: r.imported, duplicates: r.duplicates, receipt: r.receipt, fixed: r.fixed, counted: r.counted, review: r.review }),
      );
      await bookings.reload();
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function rematch() {
    setBusy(true);
    try {
      const r = await api.rematch();
      toast.success(t("bank.rematched", { matched: r.matched }));
      await bookings.reload();
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function decide(booking: BankTransaction, decision: BookingDecision) {
    try {
      const updated = await api.decide(booking.id, decision);
      bookings.setData((list) => list?.map((b) => (b.id === updated.id ? updated : b)) ?? null);
      toast.success(t("bank.decided"));
      void bookings.reload();
    } catch (error) {
      toast.error((error as Error).message);
    }
  }

  async function remove(booking: BankTransaction) {
    if (!window.confirm(t("bank.confirmDelete"))) return;
    try {
      await api.deleteTransaction(booking.id);
      bookings.setData((list) => list?.filter((b) => b.id !== booking.id) ?? null);
      toast.success(t("bank.deleted"));
      void bookings.reload();
    } catch (error) {
      toast.error((error as Error).message);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">{t("nav.bank")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("bank.hint")}</p>
      </div>

      <Tile index={0} title={t("bank.importTitle")}>
        <p className="text-sm text-muted-foreground">{t("bank.importHint")}</p>
        <div className="flex flex-wrap gap-2">
          <input
            id={`${uid}-file`}
            ref={input}
            type="file"
            accept=".csv,.xml,.txt,text/csv,application/xml,text/xml"
            className="hidden"
            data-testid="statement-input"
            aria-label={t("bank.import")}
            onChange={upload}
          />
          <Button onClick={() => input.current?.click()} disabled={busy}>
            <Upload /> {t("bank.import")}
          </Button>
          <Button variant="outline" onClick={rematch} disabled={busy}>
            <RefreshCw /> {t("bank.rematch")}
          </Button>
        </div>
      </Tile>

      <div className="glass flex gap-1 overflow-x-auto rounded-xl p-1" role="tablist" aria-label={t("bank.tabs")}>
        {FILTERS.map((value) => (
          <button
            key={value}
            role="tab"
            aria-selected={filter === value}
            onClick={() => setFilter(value)}
            className={cn(
              "whitespace-nowrap rounded-lg px-3 py-1.5 text-xs font-medium text-muted-foreground",
              filter === value && "bg-primary text-primary-foreground",
            )}
          >
            {t(`bank.${value}` as MessageKey)}
            {value === "review" && bookings.data ? ` (${count("review")})` : ""}
          </button>
        ))}
      </div>

      <TagFilter tags={tags} value={tagFilter} onChange={setTagFilter} />

      {bookings.error ? (
        <p className="glass rounded-2xl p-6 text-destructive">{bookings.error.message}</p>
      ) : !bookings.data || !categories.data || !recurring.data ? (
        <div className="space-y-2">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-16 rounded-2xl" />
          ))}
        </div>
      ) : visible.length === 0 ? (
        <p className="glass rounded-2xl p-6 text-center text-muted-foreground">{t("bank.empty")}</p>
      ) : (
        <ul className="space-y-2">
          {visible.map((booking) => (
            <BookingRow
              key={booking.id}
              booking={booking}
              categories={categories.data ?? []}
              recurring={recurring.data ?? []}
              tags={tags}
              onTagCreated={addTag}
              onDecide={(decision) => decide(booking, decision)}
              onDelete={() => void remove(booking)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
