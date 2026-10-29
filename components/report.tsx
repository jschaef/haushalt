"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";
import { ChevronDown, Download, ExternalLink, Search } from "lucide-react";
import { Tile } from "@/components/bento";
import { CustomRangeFields, RangePicker } from "@/components/dashboard";
import { TagChips } from "@/components/tags";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type Category, type ReportEntry, type ReportGroupRow } from "@/lib/api";
import { money, shortDate, validCustomRange } from "@/lib/format";
import { useData } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n/provider";
import type { Locale, MessageKey } from "@/lib/i18n/messages";
import {
  EMPTY_FILTER,
  REPORT_GROUPS,
  REPORT_SOURCES,
  activeConditions,
  euroCents,
  type Choice,
  type ReportFilter,
  type ReportGroup,
} from "@/lib/report";
import { byName } from "@/lib/sort";
import { cn } from "@/lib/utils";

// Report (Jochen, 2026-10-29): receipt lines, bookings and fixed costs with
// filters - AND between fields, OR within a field, NOT per field - sums,
// groups and a CSV export.

const SELECT_CLASS =
  "h-9 w-full min-w-0 rounded-lg border border-input bg-transparent px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50 dark:bg-input/30";

type Option = { id: number; label: string; color?: string };

// A field with several values: checkboxes (OR) and an "exclude" switch (NOT).
function ChoiceField({
  label,
  options,
  value,
  onChange,
  testId,
}: {
  label: string;
  options: Option[];
  value: Choice;
  onChange: (c: Choice) => void;
  testId: string;
}) {
  const { t } = useI18n();
  const uid = useId();
  const state = !value.ids.length
    ? t("report.any")
    : value.not
      ? t("report.notChosen", { count: value.ids.length })
      : t("report.chosen", { count: value.ids.length });
  const toggle = (id: number) =>
    onChange({ ...value, ids: value.ids.includes(id) ? value.ids.filter((x) => x !== id) : [...value.ids, id] });
  return (
    <details className="group min-w-0 rounded-lg border border-input" data-testid={testId}>
      <summary className="flex h-9 cursor-pointer list-none items-center gap-2 px-2 text-sm [&::-webkit-details-marker]:hidden">
        <span className="min-w-0 flex-1 truncate">
          <span className="font-medium">{label}</span>: <span className="text-muted-foreground">{state}</span>
        </span>
        <ChevronDown className="size-4 shrink-0 transition-transform group-open:rotate-180" aria-hidden />
      </summary>
      {/* min-w-0: a fieldset is as wide as its content by default (reflow at 320 px) */}
      <fieldset className="min-w-0 space-y-2 border-t p-2">
        <legend className="sr-only">{label}</legend>
        <label className="flex items-center gap-2 text-sm font-medium">
          <input
            type="checkbox"
            className="size-4 shrink-0 accent-primary"
            checked={value.not}
            onChange={(e) => onChange({ ...value, not: e.target.checked })}
          />
          {t("report.exclude")}
        </label>
        <ul className="max-h-56 space-y-1 overflow-y-auto">
          {options.map((option) => (
            <li key={option.id}>
              <label htmlFor={`${uid}-${option.id}`} className="flex min-w-0 items-center gap-2 text-sm">
                <input
                  id={`${uid}-${option.id}`}
                  type="checkbox"
                  className="size-4 shrink-0 accent-primary"
                  checked={value.ids.includes(option.id)}
                  onChange={() => toggle(option.id)}
                />
                {option.color && <span className="size-2.5 shrink-0 rounded-full" style={{ background: option.color }} aria-hidden />}
                <span className="min-w-0 break-words">{option.label}</span>
              </label>
            </li>
          ))}
        </ul>
      </fieldset>
    </details>
  );
}

function monthLabel(key: string, locale: Locale): string {
  const [y, m] = key.split("-").map(Number);
  return new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-GB", { month: "long", year: "numeric", timeZone: "UTC" }).format(
    new Date(Date.UTC(y, m - 1, 1)),
  );
}

export function Report() {
  const { t, locale } = useI18n();
  const uid = useId();
  const [filter, setFilter] = useState<ReportFilter>(EMPTY_FILTER);
  const [group, setGroup] = useState<ReportGroup>("category");
  const [search, setSearch] = useState("");
  const [amounts, setAmounts] = useState({ min: "", max: "" });
  const categoryList = useData(() => api.categories(), "categories");
  const tagList = useData(() => api.tags(), "tags");
  const storeList = useData(() => api.stores(), "stores");
  const accountList = useData(() => api.accounts(), "accounts");

  // typed fields ask the API once typing pauses
  useEffect(() => {
    const timer = setTimeout(
      () =>
        setFilter((current) =>
          current.q === search && current.min === amounts.min && current.max === amounts.max
            ? current
            : { ...current, q: search, min: amounts.min, max: amounts.max },
        ),
      300,
    );
    return () => clearTimeout(timer);
  }, [search, amounts]);

  const ready = filter.range !== "custom" || validCustomRange(filter.custom.start, filter.custom.end);
  const key = `${JSON.stringify(filter)}:${group}`;
  const data = useData(() => (ready ? api.report(filter, group) : Promise.resolve(null)), key);
  const update = (changes: Partial<ReportFilter>) => setFilter({ ...filter, ...changes });
  const reset = () => {
    setFilter({ ...EMPTY_FILTER, range: filter.range, custom: filter.custom });
    setSearch("");
    setAmounts({ min: "", max: "" });
  };

  const categories = categoryList.data ?? [];
  const tags = tagList.data ?? [];
  const accounts = accountList.data ?? [];
  const nameOf = (c: Category) => (locale === "de" ? c.name_de : c.name_en);
  const category = (id: number | null) => categories.find((c) => c.id === id);
  const r = data.data;

  function groupLabel(row: ReportGroupRow): string {
    if (row.key === null) return group === "tag" ? t("report.noTag") : group === "account" ? t("report.noAccount") : t("report.none");
    if (group === "month") return monthLabel(String(row.key), locale);
    if (group === "category") {
      const c = category(Number(row.key));
      return c ? nameOf(c) : t("report.none");
    }
    if (group === "tag") return tags.find((x) => x.id === row.key)?.name ?? t("report.none");
    if (group === "account") return accounts.find((x) => x.id === row.key)?.name ?? t("report.none");
    if (group === "source") return t(`report.source.${row.key}` as MessageKey);
    return String(row.key);
  }

  const invalid = (text: string) => text.trim() !== "" && euroCents(text) === null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">{t("report.title")}</h1>
          <p className="max-w-3xl text-sm text-muted-foreground">{t("report.hint")}</p>
        </div>
        <RangePicker value={filter.range} onChange={(range) => update({ range })} />
      </div>
      {filter.range === "custom" && <CustomRangeFields value={filter.custom} onChange={(custom) => update({ custom })} />}

      <section className="glass space-y-3 rounded-2xl p-3" aria-labelledby={`${uid}-filters`} data-testid="report-filters">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id={`${uid}-filters`} className="text-sm font-semibold">
            {t("report.filters")}
          </h2>
          {activeConditions(filter) > 0 && (
            <Button variant="ghost" size="sm" onClick={reset} data-testid="report-reset">
              {t("report.reset")}
            </Button>
          )}
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="min-w-0 space-y-1 sm:col-span-2">
            <Label htmlFor={`${uid}-q`} className="text-xs">
              {t("report.search")}
            </Label>
            <div className="flex flex-wrap items-center gap-3">
              <div className="relative min-w-0 flex-1">
                <Search className="pointer-events-none absolute top-1/2 left-2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
                <Input id={`${uid}-q`} type="search" value={search} maxLength={100} onChange={(e) => setSearch(e.target.value)} className="pl-8" />
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="size-4 shrink-0 accent-primary"
                  checked={filter.q_not}
                  onChange={(e) => update({ q_not: e.target.checked })}
                />
                {t("report.searchNot")}
              </label>
            </div>
          </div>
          <div className="min-w-0 space-y-1">
            <Label htmlFor={`${uid}-flow`} className="text-xs">
              {t("report.flow")}
            </Label>
            <select
              id={`${uid}-flow`}
              value={filter.flow}
              onChange={(e) => update({ flow: e.target.value as ReportFilter["flow"] })}
              className={SELECT_CLASS}
            >
              <option value="all">{t("report.flowAll")}</option>
              <option value="spending">{t("report.spending")}</option>
              <option value="income">{t("report.income")}</option>
            </select>
          </div>
          <div className="min-w-0 space-y-1">
            <Label htmlFor={`${uid}-oneoff`} className="text-xs">
              {t("report.oneOff")}
            </Label>
            <select
              id={`${uid}-oneoff`}
              value={filter.one_off}
              onChange={(e) => update({ one_off: e.target.value as ReportFilter["one_off"] })}
              className={SELECT_CLASS}
            >
              <option value="exclude">{t("report.oneOffExclude")}</option>
              <option value="include">{t("report.oneOffInclude")}</option>
              <option value="only">{t("report.oneOffOnly")}</option>
            </select>
          </div>
          <fieldset className="min-w-0 space-y-1">
            <legend className="text-xs font-medium">{t("report.sources")}</legend>
            <div className="flex flex-wrap gap-x-3 gap-y-1">
              {REPORT_SOURCES.map((source) => (
                <label key={source} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="size-4 shrink-0 accent-primary"
                    checked={filter.sources.includes(source)}
                    onChange={() =>
                      update({
                        sources: filter.sources.includes(source) ? filter.sources.filter((s) => s !== source) : [...filter.sources, source],
                      })
                    }
                  />
                  {t(`report.source.${source}`)}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="min-w-0 space-y-1">
            <Label htmlFor={`${uid}-min`} className="text-xs">
              {t("report.min")}
            </Label>
            <Input
              id={`${uid}-min`}
              inputMode="decimal"
              value={amounts.min}
              maxLength={16}
              aria-invalid={invalid(amounts.min) || undefined}
              aria-describedby={invalid(amounts.min) ? `${uid}-min-error` : undefined}
              onChange={(e) => setAmounts({ ...amounts, min: e.target.value })}
            />
            {invalid(amounts.min) && (
              <p id={`${uid}-min-error`} className="text-xs text-destructive">
                {t("report.amountInvalid")}
              </p>
            )}
          </div>
          <div className="min-w-0 space-y-1">
            <Label htmlFor={`${uid}-max`} className="text-xs">
              {t("report.max")}
            </Label>
            <Input
              id={`${uid}-max`}
              inputMode="decimal"
              value={amounts.max}
              maxLength={16}
              aria-invalid={invalid(amounts.max) || undefined}
              aria-describedby={invalid(amounts.max) ? `${uid}-max-error` : undefined}
              onChange={(e) => setAmounts({ ...amounts, max: e.target.value })}
            />
            {invalid(amounts.max) && (
              <p id={`${uid}-max-error`} className="text-xs text-destructive">
                {t("report.amountInvalid")}
              </p>
            )}
          </div>
          <div className="min-w-0 space-y-1">
            <Label htmlFor={`${uid}-group`} className="text-xs">
              {t("report.group")}
            </Label>
            <select id={`${uid}-group`} value={group} onChange={(e) => setGroup(e.target.value as ReportGroup)} className={SELECT_CLASS}>
              {REPORT_GROUPS.map((g) => (
                <option key={g} value={g}>
                  {t(`report.group.${g}`)}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <ChoiceField
            label={t("report.categories")}
            testId="choice-categories"
            options={byName(categories, nameOf, locale).map((c) => ({ id: c.id, label: nameOf(c), color: c.color }))}
            value={filter.categories}
            onChange={(categories) => update({ categories })}
          />
          <ChoiceField
            label={t("report.tags")}
            testId="choice-tags"
            options={byName(tags, (x) => x.name, locale).map((x) => ({ id: x.id, label: x.name, color: x.color }))}
            value={filter.tags}
            onChange={(tags) => update({ tags })}
          />
          <ChoiceField
            label={t("report.stores")}
            testId="choice-stores"
            options={byName(storeList.data ?? [], (s) => s.name, locale).map((s) => ({ id: s.id, label: s.name }))}
            value={filter.stores}
            onChange={(stores) => update({ stores })}
          />
          <ChoiceField
            label={t("report.accounts")}
            testId="choice-accounts"
            options={byName(accounts, (a) => a.name, locale).map((a) => ({ id: a.id, label: a.name, color: a.color }))}
            value={filter.accounts}
            onChange={(accounts) => update({ accounts })}
          />
        </div>
      </section>

      {!ready ? (
        <p className="glass rounded-2xl p-6 text-center text-muted-foreground">{t("range.incomplete")}</p>
      ) : data.error ? (
        <p className="glass rounded-2xl p-6 text-destructive">{data.error.message}</p>
      ) : !r ? (
        <Skeleton className="h-48 rounded-2xl" />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            {(
              [
                ["report.spending", money(r.spending_cents, locale), "report-spending"],
                ["report.income", money(r.income_cents, locale), "report-income"],
                ["report.balance", money(r.balance_cents, locale), "report-balance"],
                ["report.entries", String(r.count), "report-count"],
              ] as const
            ).map(([label, value, testId], index) => (
              <Tile key={label} index={index} title={t(label)} testId={testId}>
                <p className="tabular text-xl font-semibold break-words sm:text-2xl">{value}</p>
              </Tile>
            ))}
          </div>
          <div className="flex justify-end">
            <a
              href={api.reportCsvUrl(filter)}
              download
              className="inline-flex items-center gap-2 text-sm text-primary underline-offset-4 hover:underline"
              data-testid="report-csv"
            >
              <Download className="size-4" aria-hidden />
              {t("report.csv")}
            </a>
          </div>

          {group !== "none" && r.groups.length > 0 && (
            <Tile index={4} title={t("report.groups", { group: t(`report.group.${group}`) })} testId="report-groups">
              <ul className="space-y-1.5">
                {r.groups.map((row) => {
                  const c = group === "category" ? category(Number(row.key)) : undefined;
                  const color = c?.color ?? (group === "tag" ? tags.find((x) => x.id === row.key)?.color : undefined);
                  return (
                    <li key={String(row.key)} className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-0.5 text-sm" data-testid="report-group">
                      {color && <span className="size-2.5 shrink-0 rounded-full" style={{ background: color }} aria-hidden />}
                      <span className="min-w-0 flex-1 break-words">{groupLabel(row)}</span>
                      <span className="text-xs text-muted-foreground">{t("report.list", { count: row.count })}</span>
                      {row.income_cents !== 0 && <span className="tabular text-primary">+{money(row.income_cents, locale)}</span>}
                      {(row.spending_cents !== 0 || row.income_cents === 0) && (
                        <span className="tabular font-semibold">{money(row.spending_cents, locale)}</span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </Tile>
          )}

          <Tile index={5} title={t("report.list", { count: r.count })} testId="report-entries">
            {r.truncated && (
              <p className="mb-2 text-xs text-muted-foreground">{t("report.truncated", { shown: r.entries.length, count: r.count })}</p>
            )}
            {r.entries.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("report.empty")}</p>
            ) : (
              <ul className="space-y-1.5">
                {r.entries.map((entry, index) =>
                  entryRow(entry, `${entry.source}:${entry.receipt_id ?? entry.transaction_id ?? entry.recurring_id}:${entry.date}:${index}`),
                )}
              </ul>
            )}
          </Tile>
        </>
      )}
    </div>
  );

  function entryRow(entry: ReportEntry, key: string) {
    const income = entry.flow === "income";
    const c = category(entry.category_id);
    return (
      <li key={key} className="flex min-w-0 items-start gap-3 rounded-xl bg-muted/40 px-3 py-2" data-testid="report-entry">
        <span className="mt-1.5 size-2.5 shrink-0 rounded-full" style={{ background: c?.color ?? "#64748b" }} aria-hidden />
        <span className="min-w-0 flex-1">
          <span className="block font-medium break-words">{entry.rest ? t("report.rest") : entry.text || t("report.none")}</span>
          <span className="block text-xs break-words text-muted-foreground">
            {[
              shortDate(entry.date, locale) +
                (entry.until && entry.until !== entry.date ? ` ${t("report.until", { date: shortDate(entry.until, locale) })}` : ""),
              t(`report.source.${entry.source}`),
              c ? nameOf(c) : "",
              entry.detail,
              entry.account_id !== null ? accounts.find((a) => a.id === entry.account_id)?.name ?? "" : "",
            ]
              .filter(Boolean)
              .join(" · ")}
          </span>
          {entry.tag_ids.length > 0 && (
            <span className="mt-1 block">
              <TagChips ids={entry.tag_ids} tags={tags} />
            </span>
          )}
        </span>
        {entry.one_off && <span className="shrink-0 rounded-full border px-2 py-0.5 text-xs">{t("report.oneOffBadge")}</span>}
        <span className={cn("tabular shrink-0 font-semibold", income && "text-primary")}>
          {income ? "+" : ""}
          {money(entry.cents, locale)}
        </span>
        {entry.receipt_id !== null && (
          <Link href={`/receipts/${entry.receipt_id}`} className="shrink-0 text-primary" aria-label={`${t("report.openReceipt")} #${entry.receipt_id}`}>
            <ExternalLink className="size-4" />
          </Link>
        )}
      </li>
    );
  }
}
