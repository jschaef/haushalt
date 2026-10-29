"use client";

import { useTheme } from "next-themes";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import { ArrowDownRight, ArrowUpRight, Camera, CheckCircle2, ChevronRight, Upload } from "lucide-react";
import { AnimatedNumber } from "@/components/animated-number";
import { BentoGrid, Tile } from "@/components/bento";
import { Chart, type ChartOption } from "@/components/chart";
import { useScan } from "@/components/scan";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type CustomRange, type Range, type Summary } from "@/lib/api";
import { localToday, money, percentChange, shortDate, validCustomRange } from "@/lib/format";
import { useData } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";

const RANGES: Range[] = ["7d", "30d", "90d", "365d", "ytd", "all", "custom"];
// the last chosen range, per browser (Jochen, 2026-10-27)
const RANGE_KEY = "haushalt.dashboardRange";

type Chosen = { range: Range; custom: CustomRange };

function loadChosen(): Chosen | null {
  try {
    const saved = JSON.parse(window.localStorage.getItem(RANGE_KEY) ?? "null") as Chosen | null;
    return saved && RANGES.includes(saved.range) ? saved : null;
  } catch {
    return null;
  }
}

function saveChosen(chosen: Chosen) {
  try {
    window.localStorage.setItem(RANGE_KEY, JSON.stringify(chosen));
  } catch {
    // private window or blocked storage: the choice lasts until reload
  }
}

export function CustomRangeFields({ value, onChange }: { value: CustomRange; onChange: (c: CustomRange) => void }) {
  const { t } = useI18n();
  return (
    <div className="glass flex flex-wrap items-end gap-3 rounded-xl p-3" data-testid="custom-range">
      <div className="space-y-1">
        <Label htmlFor="range-start" className="text-xs">
          {t("range.start")}
        </Label>
        <Input
          id="range-start"
          type="date"
          value={value.start}
          max={localToday()}
          onChange={(e) => onChange({ ...value, start: e.target.value })}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="range-end" className="text-xs">
          {t("range.end")}
        </Label>
        <Input
          id="range-end"
          type="date"
          value={value.end}
          min={value.start || undefined}
          max={localToday()}
          aria-describedby="range-end-hint"
          onChange={(e) => onChange({ ...value, end: e.target.value })}
        />
      </div>
      <p id="range-end-hint" className="basis-full text-xs text-muted-foreground">
        {t("range.endHint")}
      </p>
    </div>
  );
}

export function RangePicker({ value, onChange }: { value: Range; onChange: (r: Range) => void }) {
  const { t } = useI18n();
  return (
    <div className="glass flex gap-1 overflow-x-auto rounded-xl p-1" role="tablist">
      {RANGES.map((range) => (
        <button
          key={range}
          role="tab"
          aria-selected={value === range}
          onClick={() => onChange(range)}
          className={cn(
            "whitespace-nowrap rounded-lg px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors",
            value === range && "bg-primary text-primary-foreground",
          )}
        >
          {t(`range.${range}`)}
        </button>
      ))}
    </div>
  );
}

function Trend({ current, previous }: { current: number; previous: number }) {
  const { t } = useI18n();
  const change = percentChange(current, previous);
  if (change === null) return null;
  const up = change > 0;
  return (
    <span className={cn("inline-flex items-center gap-1 text-xs font-medium", up ? "text-negative" : "text-positive")}>
      {up ? <ArrowUpRight className="size-3.5" /> : <ArrowDownRight className="size-3.5" />}
      {Math.abs(change).toFixed(0)} % {t("dash.vsPrevious")}
    </span>
  );
}

export function Dashboard() {
  const { t, locale } = useI18n();
  const { version, openCamera, openFiles } = useScan();
  const [chosen, setChosen] = useState<Chosen>({ range: "30d", custom: { start: "", end: "" } });
  useEffect(() => {
    const saved = loadChosen();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- localStorage exists only after hydration
    if (saved) setChosen(saved);
  }, []);
  const choose = (next: Chosen) => {
    setChosen(next);
    saveChosen(next);
  };
  const { range, custom } = chosen;
  // a custom range asks the API once its start is complete
  const ready = range !== "custom" || validCustomRange(custom.start, custom.end);
  const key = range === "custom" ? `custom:${custom.start}:${custom.end}` : range;
  const summary = useData(() => (ready ? api.summary(range, custom) : Promise.resolve(null)), `${key}:${version}`);
  const drafts = useData(() => api.receipts("draft"), `drafts:${version}`);
  const recent = useData(() => api.receipts("confirmed"), `recent:${version}`);
  const bank = useData(() => api.transactions("review"), `bank:${version}`);
  const bankCount = bank.data?.length ?? 0;
  const fmt = useCallback((cents: number) => money(cents, locale), [locale]);
  const s = summary.data;

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">{t("nav.dashboard")}</h1>
          {/* phones: the report is not in the tab bar */}
          <Link href="/report" className="text-sm text-primary underline-offset-4 hover:underline" data-testid="report-link">
            {t("nav.report")} →
          </Link>
          {s && (
            <p className="text-sm text-muted-foreground">
              {shortDate(s.start, locale)} – {shortDate(s.end, locale)} · {s.days} {t("dash.days")}
            </p>
          )}
          {s?.since && range !== "custom" && (
            <p className="text-xs text-muted-foreground" data-testid="dash-since">
              {t("dash.since", { date: shortDate(s.since, locale) })}
            </p>
          )}
        </div>
        <RangePicker value={range} onChange={(next) => choose({ ...chosen, range: next })} />
      </div>
      {range === "custom" && <CustomRangeFields value={custom} onChange={(next) => choose({ range, custom: next })} />}

      {!ready ? (
        <p className="glass rounded-2xl p-6 text-center text-muted-foreground" data-testid="range-incomplete">
          {t("range.incomplete")}
        </p>
      ) : !s ? (
        <BentoGrid>
          {[...Array(6)].map((_, i) => (
            <Skeleton key={i} className={cn("rounded-3xl", i === 0 ? "col-span-2 row-span-2 h-72" : "h-32")} />
          ))}
        </BentoGrid>
      ) : (
        <BentoGrid>
          <Tile index={0} className="col-span-2 justify-between gap-6 md:row-span-2 bg-gradient-to-br from-primary/15 to-chart-4/10" testId="tile-daily">
            <div className="text-sm font-medium text-muted-foreground">{t("dash.avgDaily")}</div>
            <div>
              <AnimatedNumber value={s.average.total.day} format={fmt} className="tabular block text-5xl font-semibold tracking-tight md:text-6xl" />
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
                <span>
                  {t("dash.variable")} <b className="tabular text-foreground">{fmt(s.average.variable.day)}</b>
                </span>
                <span>
                  {t("dash.fixed")} <b className="tabular text-foreground">{fmt(s.average.fixed.day)}</b>
                </span>
              </div>
            </div>
            <SplitBar variable={s.variable_cents} fixed={s.fixed_cents} />
          </Tile>

          <AverageTile index={1} label={t("dash.perWeek")} value={s.average.total.week} fmt={fmt} testId="tile-week" />
          <AverageTile index={2} label={t("dash.perMonth")} value={s.average.total.month} fmt={fmt} testId="tile-month" />
          <AverageTile index={3} label={t("dash.perYear")} value={s.average.total.year} fmt={fmt} testId="tile-year" />

          <Tile index={4} title={t("dash.periodTotal")} testId="tile-total" className="@container">
            <AnimatedNumber value={s.total_cents} format={fmt} className="tabular whitespace-nowrap font-semibold" style={fitAmount(fmt(s.total_cents))} />
            <Trend current={s.total_cents} previous={s.previous_total_cents} />
            <div className="text-xs text-muted-foreground">
              {s.receipt_count} {t("dash.receipts")}
            </div>
          </Tile>

          <ReviewTile index={5} count={drafts.data?.length ?? 0} />

          <Tile index={5} title={t("cash.title")} className="col-span-2 @container" testId="tile-cashflow">
            <Cashflow summary={s} fmt={fmt} />
          </Tile>

          {bankCount > 0 && (
            <Tile index={6} title={t("bank.dashTitle")} testId="tile-bank">
              <Link href="/bank" className="group flex flex-1 flex-col justify-between gap-2">
                <span className="text-3xl font-semibold text-chart-3">{bankCount}</span>
                <span className="flex items-center text-xs text-muted-foreground group-hover:text-foreground">
                  {t("bank.dashHint", { n: bankCount })} <ChevronRight className="size-3 shrink-0" />
                </span>
              </Link>
            </Tile>
          )}

          <Tile index={6} className={cn("col-span-2 justify-between bg-gradient-to-br from-chart-2/15 to-primary/10", bankCount > 0 ? "md:col-span-2" : "md:col-span-3")}>
            <div>
              <div className="text-lg font-semibold">{t("nav.scan")}</div>
              <p className="text-sm text-muted-foreground">{t("receipts.dropHint")}</p>
            </div>
            <div className="flex gap-2">
              <Button onClick={openCamera}>
                <Camera /> {t("receipts.camera")}
              </Button>
              <Button variant="outline" onClick={openFiles}>
                <Upload /> {t("receipts.choose")}
              </Button>
            </div>
          </Tile>

          <Tile index={7} title={t("dash.daily")} className="col-span-2 md:col-span-4 xl:col-span-4">
            <DailyChart summary={s} />
          </Tile>

          {s.monthly.length > 1 && (
            <Tile index={7} title={t("cash.monthly")} className="col-span-2 md:col-span-4 xl:col-span-4" testId="tile-monthly">
              <MonthlyChart summary={s} />
            </Tile>
          )}

          <Tile index={8} title={t("dash.categories")} className="col-span-2 row-span-2">
            <CategoryBreakdown summary={s} />
          </Tile>

          <Tile index={9} title={t("dash.stores")} className="col-span-2">
            <StoreList summary={s} fmt={fmt} />
          </Tile>

          {s.by_tag.length > 0 && (
            <Tile index={10} title={t("tags.dashTitle")} className="col-span-2" testId="tile-tags">
              <TagSums summary={s} fmt={fmt} />
            </Tile>
          )}


          <Tile index={10} title={t("receipts.confirmed")} className="col-span-2" action={<MoreLink href="/receipts" />}>
            <ul className="divide-y divide-border/60 text-sm">
              {(recent.data ?? []).slice(0, 4).map((r) => (
                <li key={r.id}>
                  <Link href={`/receipts/${r.id}`} className="flex items-center justify-between py-2 hover:text-primary">
                    <span className="truncate">{r.store_name || t("receipts.unknownStore")}</span>
                    <span className="tabular text-muted-foreground">{fmt(r.total_cents)}</span>
                  </Link>
                </li>
              ))}
              {recent.data?.length === 0 && <li className="py-2 text-muted-foreground">{t("dash.empty")}</li>}
            </ul>
          </Tile>
        </BentoGrid>
      )}
    </div>
  );
}

function MoreLink({ href }: { href: string }) {
  return (
    <Link href={href} className="text-muted-foreground hover:text-foreground" aria-label="more">
      <ChevronRight className="size-4" />
    </Link>
  );
}

// Amounts in the small tiles: text-2xl, and only as much smaller as the
// text needs to fit the tile (phones, larger text of the low-vision modes)
// instead of being cut off. A tabular digit is about 0.62 em wide; cqi is
// 1 % of the tile's content width (the tile is the size container).
function fitAmount(text: string): CSSProperties {
  return { fontSize: `min(1.5rem, ${(100 / (text.length * 0.62)).toFixed(1)}cqi)` };
}

function AverageTile({ index, label, value, fmt, testId }: { index: number; label: string; value: number; fmt: (v: number) => string; testId: string }) {
  return (
    <Tile index={index} title={label} testId={testId} className="@container justify-between">
      <AnimatedNumber value={value} format={fmt} className="tabular whitespace-nowrap font-semibold tracking-tight" style={fitAmount(fmt(value))} />
    </Tile>
  );
}

// income against spending in the period; open bookings are shown apart, so
// an incomplete month does not look like overspending (or like savings)
function Cashflow({ summary: s, fmt }: { summary: Summary; fmt: (v: number) => string }) {
  const { t, locale } = useI18n();
  const signed = (cents: number) => (cents > 0 ? `+${fmt(cents)}` : fmt(cents));
  return (
    <div className="flex flex-1 flex-col justify-between gap-3">
      <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1 text-sm">
        <dt className="text-muted-foreground">{t("cash.income")}</dt>
        <dd className="tabular text-right font-medium text-positive" data-testid="cash-income">
          {signed(s.income_cents)}
        </dd>
        <dt className="text-muted-foreground">{t("cash.spending")}</dt>
        <dd className="tabular text-right font-medium" data-testid="cash-spending">
          {fmt(-s.total_cents)}
        </dd>
        <dt className="border-t border-border/60 pt-1 font-medium">{t("cash.balance")}</dt>
        <dd
          className={cn("tabular border-t border-border/60 pt-1 text-right font-semibold", s.balance_cents < 0 ? "text-negative" : "text-positive")}
          data-testid="cash-balance"
        >
          {signed(s.balance_cents)}
        </dd>
        {s.saved_cents !== 0 && (
          <>
            <dt className="pl-3 text-muted-foreground">{t("cash.saved")}</dt>
            <dd className="tabular text-right" data-testid="cash-saved">
              {fmt(s.saved_cents)}
            </dd>
          </>
        )}
        {s.savings_rate !== null && (
          <>
            <dt className="text-muted-foreground">{t("cash.rate")}</dt>
            <dd className="tabular text-right" data-testid="cash-rate">
              {new Intl.NumberFormat(locale === "de" ? "de-DE" : "en-GB", { style: "percent", maximumFractionDigits: 0 }).format(s.savings_rate)}
            </dd>
          </>
        )}
      </dl>
      {s.one_off.count > 0 && (
        <p className="text-xs text-muted-foreground" data-testid="cash-one-off">
          {t("cash.oneOff", { in: signed(s.one_off.in_cents), out: fmt(-s.one_off.out_cents) })}
        </p>
      )}
      {s.open.count > 0 ? (
        <Link href="/bank" className="group flex items-start gap-1 text-xs text-muted-foreground hover:text-foreground" data-testid="cash-open">
          <span>
            {t("cash.open", { n: s.open.count, out: fmt(s.open.out_cents), in: fmt(s.open.in_cents) })}
          </span>
          <ChevronRight className="mt-0.5 size-3 shrink-0" />
        </Link>
      ) : (
        s.income_cents === 0 && <p className="text-xs text-muted-foreground">{t("cash.noIncome")}</p>
      )}
    </div>
  );
}

function MonthlyChart({ summary }: { summary: Summary }) {
  const { t, locale } = useI18n();
  const { resolvedTheme } = useTheme();
  // two clearly different solid colors in every theme (WCAG 1.4.11)
  const [incomeColor, spendingColor] =
    resolvedTheme === "contrast" ? ["#ffe600", "#ffffff"] : resolvedTheme === "contrast-light" ? ["#0033a0", "#000000"] : ["#16a34a", "#8b7dff"];
  const option = useMemo<ChartOption>(() => {
    const tag = locale === "de" ? "de-DE" : "en-GB";
    const label = new Intl.DateTimeFormat(tag, { month: "short", year: "2-digit" });
    return {
      grid: { left: 8, right: 8, top: 10, bottom: 4, containLabel: true },
      tooltip: { trigger: "axis", valueFormatter: (v: unknown) => money(Number(v) * 100, locale) },
      xAxis: {
        type: "category",
        data: summary.monthly.map((m) => label.format(new Date(`${m.month}-15T12:00:00`))),
        axisTick: { show: false },
        axisLine: { show: false },
      },
      yAxis: { type: "value", splitLine: { lineStyle: { opacity: 0.15 } }, axisLabel: { formatter: (v: number) => `${v} €` } },
      series: [
        { name: t("cash.income"), type: "bar", data: summary.monthly.map((m) => m.income_cents / 100), itemStyle: { color: incomeColor, borderRadius: [4, 4, 0, 0] }, barMaxWidth: 16 },
        { name: t("cash.spending"), type: "bar", data: summary.monthly.map((m) => m.spending_cents / 100), itemStyle: { color: spendingColor, borderRadius: [4, 4, 0, 0] }, barMaxWidth: 16 },
      ],
    };
  }, [summary, locale, t, incomeColor, spendingColor]);
  return (
    <div className="space-y-2">
      <Chart option={option} className="h-56 w-full" label={t("cash.monthly")} />
      {/* the numbers behind the bars for screen readers (WCAG 1.1.1); sr-only
          sits on a div: a table ignores the 1 px width and widens the page */}
      <div className="sr-only">
        <table>
          <caption>{t("cash.monthly")}</caption>
          <thead>
            <tr>
              <th scope="col">{t("cash.month")}</th>
              <th scope="col">{t("cash.income")}</th>
              <th scope="col">{t("cash.spending")}</th>
            </tr>
          </thead>
          <tbody>
            {summary.monthly.map((m) => (
              <tr key={m.month}>
                <th scope="row">{m.month}</th>
                <td>{money(m.income_cents, locale)}</td>
                <td>{money(m.spending_cents, locale)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm ring-1 ring-foreground/40" style={{ background: incomeColor }} aria-hidden /> {t("cash.income")}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm ring-1 ring-foreground/40" style={{ background: spendingColor }} aria-hidden /> {t("cash.spending")}
        </span>
      </div>
    </div>
  );
}

function SplitBar({ variable, fixed }: { variable: number; fixed: number }) {
  const { t } = useI18n();
  const total = variable + fixed;
  const share = total ? (variable / total) * 100 : 0;
  return (
    <div className="space-y-1.5">
      <div className="flex h-2 overflow-hidden rounded-full bg-muted">
        <div className="bg-primary transition-[width] duration-700" style={{ width: `${share}%` }} />
        <div className="bg-chart-3 transition-[width] duration-700" style={{ width: `${total ? 100 - share : 0}%` }} />
      </div>
      <div className="flex justify-between text-[11px] text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="size-2 rounded-full bg-primary" /> {t("dash.variable")}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2 rounded-full bg-chart-3" /> {t("dash.fixed")}
        </span>
      </div>
    </div>
  );
}

function ReviewTile({ index, count }: { index: number; count: number }) {
  const { t } = useI18n();
  return (
    <Tile index={index} title={t("dash.toReview")} testId="tile-review">
      {count ? (
        <Link href="/receipts?status=draft" className="group flex flex-1 flex-col justify-between">
          <span className="text-3xl font-semibold text-chart-3">{count}</span>
          <span className="flex items-center text-xs text-muted-foreground group-hover:text-foreground">
            {t("dash.toReviewHint")} <ChevronRight className="size-3" />
          </span>
        </Link>
      ) : (
        <div className="flex flex-1 items-center gap-2 text-sm text-positive">
          <CheckCircle2 className="size-5" /> {t("dash.allReviewed")}
        </div>
      )}
    </Tile>
  );
}

function DailyChart({ summary }: { summary: Summary }) {
  const { t, locale } = useI18n();
  const { resolvedTheme } = useTheme();
  // solid bars in the low-vision modes (--primary of app/globals.css)
  const solid = resolvedTheme === "contrast" ? "#ffe600" : resolvedTheme === "contrast-light" ? "#0033a0" : null;
  const option = useMemo<ChartOption>(() => {
    const tag = locale === "de" ? "de-DE" : "en-GB";
    const label = new Intl.DateTimeFormat(tag, { day: "2-digit", month: "2-digit" });
    return {
      grid: { left: 8, right: 8, top: 10, bottom: 4, containLabel: true },
      tooltip: { trigger: "axis", valueFormatter: (v: unknown) => money(Number(v) * 100, locale) },
      xAxis: {
        type: "category",
        data: summary.daily.map((d) => label.format(new Date(`${d.date}T12:00:00`))),
        axisTick: { show: false },
        axisLine: { show: false },
      },
      yAxis: { type: "value", splitLine: { lineStyle: { opacity: 0.15 } }, axisLabel: { formatter: (v: number) => `${v} €` } },
      series: [
        {
          type: "bar",
          data: summary.daily.map((d) => d.cents / 100),
          itemStyle: {
            borderRadius: [6, 6, 2, 2],
            color:
              solid ?? { type: "linear", x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: "#8b7dff" }, { offset: 1, color: "#ff6fae" }] },
          },
          barMaxWidth: 18,
        },
      ],
    };
  }, [summary, locale, solid]);
  return <Chart option={option} className="h-56 w-full" label={t("dash.daily")} />;
}

function CategoryBreakdown({ summary }: { summary: Summary }) {
  const { t, locale } = useI18n();
  const { resolvedTheme } = useTheme();
  // low-vision modes: the category colors are the household's choice, so the
  // segments get an outline in the text color (WCAG 1.4.11, 3:1 for graphics)
  const outline = resolvedTheme === "contrast" ? "#ffffff" : resolvedTheme === "contrast-light" ? "#000000" : null;
  const total = summary.by_category.reduce((sum, c) => sum + c.cents, 0);
  const option = useMemo<ChartOption>(
    () => ({
      tooltip: { trigger: "item", valueFormatter: (v: unknown) => money(Number(v), locale) },
      series: [
        {
          type: "pie",
          radius: ["62%", "88%"],
          padAngle: 2,
          itemStyle: outline ? { borderRadius: 6, borderColor: outline, borderWidth: 2 } : { borderRadius: 6 },
          label: { show: false },
          data: summary.by_category.map((c) => ({
            name: locale === "de" ? c.name_de : c.name_en,
            value: c.cents,
            itemStyle: { color: c.color },
          })),
        },
      ],
    }),
    [summary, locale, outline],
  );
  if (!total) return <p className="text-sm text-muted-foreground">{t("dash.empty")}</p>;
  return (
    <div className="flex flex-col gap-3">
      <Chart option={option} className="mx-auto h-44 w-44" label={t("dash.categories")} />
      <ul className="space-y-1.5 text-sm">
        {summary.by_category.slice(0, 7).map((c) => (
          <li key={c.key} className="flex items-center gap-2">
            <span className={cn("size-2.5 rounded-full", outline && "ring-2 ring-foreground")} style={{ background: c.color }} />
            <span className="flex-1 truncate">{locale === "de" ? c.name_de : c.name_en}</span>
            <span className="tabular text-muted-foreground">{money(c.cents, locale)}</span>
            <span className="tabular w-10 text-right text-xs text-muted-foreground">{((c.cents / total) * 100).toFixed(0)} %</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// tags overlap, so no shares: each row is the full amount of its entries
function TagSums({ summary, fmt }: { summary: Summary; fmt: (v: number) => string }) {
  const { t } = useI18n();
  return (
    <div className="space-y-2">
      <ul className="space-y-1.5 text-sm">
        {summary.by_tag.map((tag) => (
          <li key={tag.id} className="flex items-center gap-2">
            <span className="size-2.5 shrink-0 rounded-full ring-1 ring-foreground/40" style={{ background: tag.color }} aria-hidden />
            <span className="flex-1 truncate">{tag.name}</span>
            <span className="tabular text-muted-foreground">{fmt(tag.cents)}</span>
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted-foreground">{t("tags.dashHint")}</p>
    </div>
  );
}

function StoreList({ summary, fmt }: { summary: Summary; fmt: (v: number) => string }) {
  const { t } = useI18n();
  const max = Math.max(1, ...summary.by_store.map((s) => s.cents));
  if (!summary.by_store.length) return <p className="text-sm text-muted-foreground">{t("dash.empty")}</p>;
  return (
    <ul className="space-y-2.5 text-sm">
      {summary.by_store.slice(0, 5).map((store) => (
        <li key={store.name} className="space-y-1">
          <div className="flex justify-between">
            <span className="truncate">{store.name}</span>
            <span className="tabular text-muted-foreground">
              {fmt(store.cents)} · {store.count}×
            </span>
          </div>
          <div className="h-1.5 rounded-full bg-muted">
            <div className="h-full rounded-full bg-gradient-to-r from-primary to-chart-4" style={{ width: `${(store.cents / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}
