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
import {
  api,
  type BankAccount,
  type BankTransaction,
  type BookingDecision,
  type BookingStatus,
  type Category,
  type ReceiptCandidate,
  type Recurring,
  type Tag,
} from "@/lib/api";
import { SORT_KEYS, bookingYears, filterBookings, sortBookings, type CategoryFilter, type SortKey } from "@/lib/bank-view";
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

// "income": every booking with money coming in, whatever its status
type Filter = BookingStatus | "income" | "all";
const FILTERS: Filter[] = ["review", "receipt", "fixed", "counted", "ignored", "income", "all"];

const ibanKey = (iban: string) => iban.replace(/\s/g, "").toUpperCase();

// rows rendered at once; thousands of bookings would slow phones down
const PAGE = 100;

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
  accounts,
  ownIbans,
  tags,
  onTagCreated,
  onDecide,
  onDelete,
}: {
  booking: BankTransaction;
  categories: Category[];
  recurring: Recurring[];
  accounts: BankAccount[];
  ownIbans: Set<string>;
  onDecide: (decision: BookingDecision) => Promise<void>;
  onDelete: () => void;
} & TagProps) {
  const { t, locale } = useI18n();
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const category = categories.find((c) => c.id === booking.category_id);
  const cost = recurring.find((r) => r.id === booking.recurring_id);
  const account = accounts.find((a) => a.id === booking.account_id);
  // money moved between two own accounts: ignored, it is no spending
  const transfer = booking.status === "ignored" && booking.iban !== "" && ownIbans.has(ibanKey(booking.iban));

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
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
            <span>{shortDate(booking.booked_on, locale)}</span>
            {account && (
              <span className="inline-flex min-w-0 items-center gap-1" data-testid="booking-account">
                <span className="size-2 shrink-0 rounded-full ring-1 ring-foreground/40" style={{ background: account.color }} aria-hidden />
                <span className="truncate">{account.name}</span>
              </span>
            )}
          </div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className={cn("tabular font-semibold", booking.amount_cents < 0 ? "text-negative" : "text-positive")}>
            {money(booking.amount_cents, locale, booking.currency)}
          </span>
          <Badge className={BADGE_CLASS[booking.status]}>
            {booking.settles_account_id !== null ? t("bank.settlement") : transfer ? t("bank.transfer") : t(`bank.${booking.status}`)}
          </Badge>
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
  const { t, locale } = useI18n();
  const uid = useId();
  const input = useRef<HTMLInputElement>(null);
  const [filter, setFilter] = useState<Filter>("review");
  const [busy, setBusy] = useState(false);
  const bookings = useData(() => api.transactions(), "bank");
  const categories = useData(() => api.categories(), "categories");
  const recurring = useData(() => api.recurring(), "recurring");
  const tagList = useData(() => api.tags(), "tags");
  const accountList = useData(() => api.accounts(), "accounts");
  const [tagFilter, setTagFilter] = useState<number | null>(null);
  const [accountFilter, setAccountFilter] = useState<number | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("date_desc");
  const [categoryFilter, setCategoryFilter] = useState<CategoryFilter>(null);
  const [year, setYear] = useState<number | null>(null);
  const [shown, setShown] = useState(PAGE);
  // the account a statement is imported into; "" = recognised from its IBAN
  const [importAccount, setImportAccount] = useState("");
  const accounts = accountList.data ?? [];
  const ownIbans = new Set(accounts.map((a) => a.iban).filter(Boolean));

  const all = bookings.data ?? [];
  const tags = tagList.data ?? [];
  const addTag = (tag: Tag) => tagList.setData([...tags, tag].sort((a, b) => a.name.localeCompare(b.name)));
  const tagsOf = (b: BankTransaction) => (b.status === "fixed" ? (recurring.data?.find((r) => r.id === b.recurring_id)?.tag_ids ?? []) : b.tag_ids);
  const inView = (b: BankTransaction, view: Filter) => view === "all" || (view === "income" ? b.amount_cents > 0 : b.status === view);
  const count = (status: Filter) => all.filter((b) => inView(b, status)).length;
  const visible = sortBookings(
    filterBookings(
      all.filter(
        (b) => inView(b, filter) && (tagFilter === null || tagsOf(b).includes(tagFilter)) && (accountFilter === null || b.account_id === accountFilter),
      ),
      { category: categoryFilter, year },
      recurring.data ?? [],
    ),
    sortKey,
    { categories: categories.data ?? [], recurring: recurring.data ?? [], locale },
  );
  const years = bookingYears(all);
  // a changed view starts at the top again
  const change =
    <T,>(set: (value: T) => void) =>
    (value: T) => {
      set(value);
      setShown(PAGE);
    };

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy(true);
    try {
      const r = await api.importStatement(file, importAccount ? Number(importAccount) : null);
      toast.success(
        [
          t("bank.imported", { imported: r.imported, duplicates: r.duplicates, receipt: r.receipt, fixed: r.fixed, counted: r.counted, review: r.review }),
          r.account_name ? t("bank.importedTo", { name: r.account_name }) : "",
          r.transfers ? t("bank.transfers", { n: r.transfers }) : "",
          r.settlements ? t("bank.settlements", { n: r.settlements }) : "",
        ]
          .filter(Boolean)
          .join(" "),
      );
      await Promise.all([bookings.reload(), accountList.reload()]);
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
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-0 space-y-1.5">
            <Label htmlFor={`${uid}-account`}>{t("bank.account")}</Label>
            <select
              id={`${uid}-account`}
              value={importAccount}
              onChange={(e) => setImportAccount(e.target.value)}
              className={cn(SELECT_CLASS, "min-w-48")}
              data-testid="import-account"
            >
              <option value="">{t("bank.accountAuto")}</option>
              {byName(accounts, (a) => a.name, locale).map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </div>
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
            onClick={() => change(setFilter)(value)}
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

      <TagFilter tags={tags} value={tagFilter} onChange={change(setTagFilter)} />
      {accounts.length > 1 && (
        <TagFilter
          tags={byName(accounts, (a) => a.name, locale)}
          value={accountFilter}
          onChange={change(setAccountFilter)}
          label={t("bank.accountFilter")}
          allLabel={t("bank.allAccounts")}
          testId="account-filter"
        />
      )}

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3" data-testid="bank-toolbar">
        <div className="min-w-0 space-y-1">
          <Label htmlFor={`${uid}-sort`} className="text-xs">
            {t("bank.sort")}
          </Label>
          <select id={`${uid}-sort`} value={sortKey} onChange={(e) => change(setSortKey)(e.target.value as SortKey)} className={SELECT_CLASS}>
            {SORT_KEYS.map((key) => (
              <option key={key} value={key}>
                {t(`bank.sort.${key}` as MessageKey)}
              </option>
            ))}
          </select>
        </div>
        <div className="min-w-0 space-y-1">
          <Label htmlFor={`${uid}-catfilter`} className="text-xs">
            {t("bank.categoryFilter")}
          </Label>
          <select
            id={`${uid}-catfilter`}
            value={categoryFilter === null ? "" : String(categoryFilter)}
            onChange={(e) => change(setCategoryFilter)(e.target.value === "" ? null : e.target.value === "none" ? "none" : Number(e.target.value))}
            className={SELECT_CLASS}
          >
            <option value="">{t("bank.allCategories")}</option>
            <option value="none">{t("bank.noCategory")}</option>
            {byName(categories.data ?? [], (c) => categoryName(c, locale), locale).map((c) => (
              <option key={c.id} value={c.id}>
                {categoryName(c, locale)}
              </option>
            ))}
          </select>
        </div>
        <div className="min-w-0 space-y-1">
          <Label htmlFor={`${uid}-year`} className="text-xs">
            {t("bank.year")}
          </Label>
          <select
            id={`${uid}-year`}
            value={year ?? ""}
            onChange={(e) => change(setYear)(e.target.value ? Number(e.target.value) : null)}
            className={SELECT_CLASS}
          >
            <option value="">{t("bank.allYears")}</option>
            {years.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </div>
      </div>

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
          {visible.slice(0, shown).map((booking) => (
            <BookingRow
              key={booking.id}
              booking={booking}
              categories={categories.data ?? []}
              recurring={recurring.data ?? []}
              accounts={accounts}
              ownIbans={ownIbans}
              tags={tags}
              onTagCreated={addTag}
              onDecide={(decision) => decide(booking, decision)}
              onDelete={() => void remove(booking)}
            />
          ))}
        </ul>
      )}
      {visible.length > shown && (
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="outline" onClick={() => setShown((n) => n + PAGE)}>
            {t("bank.showMore", { n: Math.min(PAGE, visible.length - shown) })}
          </Button>
          <span className="text-sm text-muted-foreground">{t("bank.shownOf", { shown, total: visible.length })}</span>
        </div>
      )}
    </div>
  );
}
