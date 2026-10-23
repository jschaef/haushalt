"use client";

import { useTheme } from "next-themes";
import Link from "next/link";
import { useCallback, useMemo, useState } from "react";
import { ArrowDownRight, ArrowUpRight, Camera, CheckCircle2, ChevronRight, Upload } from "lucide-react";
import { AnimatedNumber } from "@/components/animated-number";
import { BentoGrid, Tile } from "@/components/bento";
import { Chart, type ChartOption } from "@/components/chart";
import { useScan } from "@/components/scan";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type Range, type Summary } from "@/lib/api";
import { money, percentChange, shortDate } from "@/lib/format";
import { useData } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";

const RANGES: Range[] = ["7d", "30d", "90d", "365d", "ytd", "all"];

function RangePicker({ value, onChange }: { value: Range; onChange: (r: Range) => void }) {
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
  const [range, setRange] = useState<Range>("30d");
  const summary = useData(() => api.summary(range), `${range}:${version}`);
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
          {s && (
            <p className="text-sm text-muted-foreground">
              {shortDate(s.start, locale)} – {shortDate(s.end, locale)} · {s.days} {t("dash.days")}
            </p>
          )}
        </div>
        <RangePicker value={range} onChange={setRange} />
      </div>

      {!s ? (
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

          <Tile index={4} title={t("dash.periodTotal")} testId="tile-total">
            <AnimatedNumber value={s.total_cents} format={fmt} className="tabular text-2xl font-semibold" />
            <Trend current={s.total_cents} previous={s.previous_total_cents} />
            <div className="text-xs text-muted-foreground">
              {s.receipt_count} {t("dash.receipts")}
            </div>
          </Tile>

          <ReviewTile index={5} count={drafts.data?.length ?? 0} />

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

          <Tile index={8} title={t("dash.categories")} className="col-span-2 row-span-2">
            <CategoryBreakdown summary={s} />
          </Tile>

          <Tile index={9} title={t("dash.stores")} className="col-span-2">
            <StoreList summary={s} fmt={fmt} />
          </Tile>


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

function AverageTile({ index, label, value, fmt, testId }: { index: number; label: string; value: number; fmt: (v: number) => string; testId: string }) {
  return (
    <Tile index={index} title={label} testId={testId} className="justify-between">
      <AnimatedNumber value={value} format={fmt} className="tabular text-2xl font-semibold tracking-tight" />
    </Tile>
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
