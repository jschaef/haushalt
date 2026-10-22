"use client";

import Link from "next/link";
import { useId, useMemo, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { Camera, ChevronDown, ChevronRight, Droplet, ExternalLink, Flame, Gauge, Pencil, Plus, Thermometer, Trash2, Upload, Zap } from "lucide-react";
import { toast } from "sonner";
import { Chart, type ChartOption } from "@/components/chart";
import { Tile } from "@/components/bento";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  api,
  type Category,
  type Meter,
  type MeterPhotoResult,
  type MeterSummary,
  type UtilityBill,
  type UtilityKind,
} from "@/lib/api";
import { centsToInput, money, parseMoney, shortDate } from "@/lib/format";
import { useData } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n/provider";
import type { Locale, MessageKey } from "@/lib/i18n/messages";
import { cn } from "@/lib/utils";

const SELECT_CLASS =
  "h-8 w-full appearance-none rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50 dark:bg-input/30";

const KINDS: UtilityKind[] = ["electricity", "gas", "water", "heat", "other"];
const KIND_ICON: Record<UtilityKind, typeof Zap> = {
  electricity: Zap,
  gas: Flame,
  water: Droplet,
  heat: Thermometer,
  other: Gauge,
};

type Translate = (key: MessageKey, vars?: Record<string, string | number>) => string;
type MeterBody = Omit<Meter, "id" | "last_reading">;

function today(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

function defaultUnit(kind: UtilityKind): string {
  if (kind === "electricity" || kind === "heat") return "kWh";
  if (kind === "gas" || kind === "water") return "m³";
  return "";
}

// "1234,5" / "1234.5" -> number; null for anything else (no sign, no thousands separator)
function parseDecimal(text: string): number | null {
  const cleaned = text.replace(/\s/g, "");
  if (!/^\d+([.,]\d+)?$/.test(cleaned)) return null;
  return Number(cleaned.replace(",", "."));
}

function decimalToInput(value: number, locale: Locale): string {
  const text = String(value);
  return locale === "de" ? text.replace(".", ",") : text;
}

function num(value: number, locale: Locale, digits = 2): string {
  return new Intl.NumberFormat(locale === "de" ? "de-DE" : "en-GB", { maximumFractionDigits: digits }).format(value);
}

function categoryName(category: Category, locale: Locale): string {
  return locale === "de" ? category.name_de : category.name_en;
}

function apiMessage(error: unknown, t: Translate): string {
  const message = (error as Error).message;
  if (message === "not_a_meter") return t("util.notAMeter");
  if (message === "not_a_bill") return t("util.billError.not_a_bill");
  return message;
}

function Balance({ cents, className, testId }: { cents: number; className?: string; testId?: string }) {
  const { t, locale } = useI18n();
  const positive = cents >= 0;
  return (
    <span
      data-testid={testId}
      data-value={testId ? cents : undefined}
      className={cn("font-semibold", positive ? "text-positive" : "text-negative", className)}
    >
      {positive ? t("util.credit") : t("util.extra")} <span className="tabular">{money(Math.abs(cents), locale)}</span>
    </span>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="tabular truncate text-sm font-medium">{value}</dd>
    </div>
  );
}

/* ---------- meter form (add and edit) ---------- */

function MeterForm({
  initial,
  categories,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial?: Meter;
  categories: Category[];
  submitLabel: string;
  onSubmit: (body: MeterBody) => Promise<boolean>;
  onCancel?: () => void;
}) {
  const { t, locale } = useI18n();
  const uid = useId();
  const sorted = useMemo(
    () => [...categories.filter((c) => c.kind === "fixed"), ...categories.filter((c) => c.kind !== "fixed")],
    [categories],
  );
  const categoryFor = (kind: UtilityKind) => categories.find((c) => c.key === kind)?.id ?? null;
  const [name, setName] = useState(initial?.name ?? "");
  const [kind, setKind] = useState<UtilityKind>(initial?.kind ?? "electricity");
  const [unit, setUnit] = useState(initial?.unit ?? defaultUnit("electricity"));
  const [unitTouched, setUnitTouched] = useState(Boolean(initial));
  const [number, setNumber] = useState(initial?.meter_number ?? "");
  const [categoryId, setCategoryId] = useState<number | null>(initial ? initial.category_id : categoryFor("electricity"));
  const [categoryTouched, setCategoryTouched] = useState(Boolean(initial));
  const [busy, setBusy] = useState(false);
  const valid = name.trim() !== "" && unit.trim() !== "";

  function changeKind(next: UtilityKind) {
    setKind(next);
    if (!unitTouched) setUnit(defaultUnit(next));
    if (!categoryTouched) setCategoryId(categoryFor(next));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!valid) return;
    setBusy(true);
    try {
      const ok = await onSubmit({ name: name.trim(), kind, unit: unit.trim(), meter_number: number.trim(), category_id: categoryId });
      if (ok && !initial) {
        setName("");
        setNumber("");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <div className="space-y-1.5">
        <Label htmlFor={`${uid}-name`}>{t("util.name")}</Label>
        <Input id={`${uid}-name`} value={name} onChange={(e) => setName(e.target.value)} required />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${uid}-kind`}>{t("util.kind")}</Label>
        <select id={`${uid}-kind`} value={kind} onChange={(e) => changeKind(e.target.value as UtilityKind)} className={SELECT_CLASS}>
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {t(`util.kind.${k}`)}
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${uid}-unit`}>{t("util.unit")}</Label>
        <Input
          id={`${uid}-unit`}
          value={unit}
          maxLength={16}
          onChange={(e) => {
            setUnit(e.target.value);
            setUnitTouched(true);
          }}
          required
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${uid}-number`}>{t("util.number")}</Label>
        <Input id={`${uid}-number`} value={number} maxLength={64} onChange={(e) => setNumber(e.target.value)} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${uid}-category`}>{t("receipt.category")}</Label>
        <select
          id={`${uid}-category`}
          value={categoryId ?? ""}
          onChange={(e) => {
            setCategoryId(e.target.value ? Number(e.target.value) : null);
            setCategoryTouched(true);
          }}
          className={SELECT_CLASS}
        >
          <option value="">{t("receipt.uncategorized")}</option>
          {sorted.map((c) => (
            <option key={c.id} value={c.id}>
              {categoryName(c, locale)}
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-wrap items-end gap-2">
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

/* ---------- photo proposal ---------- */

type Proposal = { photo: MeterPhotoResult; meterId: string; readOn: string; value: string };

function PhotoConfirm({
  proposal,
  meters,
  onChange,
  onSaved,
  onCancel,
}: {
  proposal: Proposal;
  meters: Meter[];
  onChange: (next: Proposal) => void;
  onSaved: () => Promise<void>;
  onCancel: () => void;
}) {
  const { t } = useI18n();
  const uid = useId();
  const [busy, setBusy] = useState(false);
  const value = parseDecimal(proposal.value);
  const valid = proposal.meterId !== "" && proposal.readOn !== "" && value !== null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!valid || value === null) return;
    setBusy(true);
    try {
      await api.addReading(Number(proposal.meterId), { read_on: proposal.readOn, value, source: "photo" });
      toast.success(t("util.readingSaved"));
      await onSaved();
    } catch (error) {
      toast.error(apiMessage(error, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Tile index={0} title={t("util.photoReading")} testId="photo-confirm">
      <p className="text-xs text-muted-foreground">
        {t("util.photoDetected", {
          kind: t(`util.kind.${proposal.photo.kind}`),
          number: proposal.photo.meter_number || "–",
        })}
      </p>
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-3">
        <div className="space-y-1.5">
          <Label htmlFor={`${uid}-meter`}>{t("util.meter")}</Label>
          <select
            id={`${uid}-meter`}
            value={proposal.meterId}
            onChange={(e) => onChange({ ...proposal, meterId: e.target.value })}
            className={SELECT_CLASS}
          >
            <option value="">{t("util.pickMeter")}</option>
            {meters.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`${uid}-date`}>{t("util.date")}</Label>
          <Input id={`${uid}-date`} type="date" value={proposal.readOn} onChange={(e) => onChange({ ...proposal, readOn: e.target.value })} required />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`${uid}-value`}>{t("util.reading")}</Label>
          <Input
            id={`${uid}-value`}
            inputMode="decimal"
            value={proposal.value}
            aria-invalid={value === null}
            onChange={(e) => onChange({ ...proposal, value: e.target.value })}
            className="tabular text-right"
          />
        </div>
        <div className="flex gap-2 sm:col-span-3">
          <Button type="submit" disabled={busy || !valid}>
            {t("common.save")}
          </Button>
          <Button type="button" variant="ghost" onClick={onCancel}>
            {t("common.cancel")}
          </Button>
        </div>
      </form>
    </Tile>
  );
}

/* ---------- meter card ---------- */

function IntervalChart({ summary, unit }: { summary: MeterSummary; unit: string }) {
  const { t, locale } = useI18n();
  const option = useMemo<ChartOption>(
    () => ({
      grid: { left: 8, right: 8, top: 10, bottom: 4, containLabel: true },
      tooltip: { trigger: "axis", valueFormatter: (v: unknown) => `${num(Number(v), locale)} ${unit}` },
      xAxis: {
        type: "category",
        data: summary.intervals.map((i) => shortDate(i.end, locale)),
        axisTick: { show: false },
        axisLine: { show: false },
      },
      yAxis: { type: "value", splitLine: { lineStyle: { opacity: 0.15 } } },
      series: [
        {
          type: "bar",
          data: summary.intervals.map((i) => i.per_day),
          itemStyle: {
            borderRadius: [6, 6, 2, 2],
            color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: "#8b7dff" }, { offset: 1, color: "#ff6fae" }] },
          },
          barMaxWidth: 28,
        },
      ],
    }),
    [summary, unit, locale],
  );
  return <Chart option={option} className="h-32 w-full" label={`${t("util.intervals")} (${unit})`} />;
}

function ReadingsSection({ meter, onChanged }: { meter: Meter; onChanged: () => Promise<void> }) {
  const { t, locale } = useI18n();
  const uid = useId();
  const readings = useData(() => api.readings(meter.id), `readings:${meter.id}`);
  const [date, setDate] = useState(today());
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const parsed = parseDecimal(value);

  async function add(event: FormEvent) {
    event.preventDefault();
    if (parsed === null || !date) return;
    setBusy(true);
    try {
      await api.addReading(meter.id, { read_on: date, value: parsed, source: "manual" });
      toast.success(t("util.readingSaved"));
      setValue("");
      await Promise.all([readings.reload(), onChanged()]);
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    try {
      await api.deleteReading(id);
      await Promise.all([readings.reload(), onChanged()]);
    } catch (error) {
      toast.error((error as Error).message);
    }
  }

  const list = [...(readings.data ?? [])].sort((a, b) => b.read_on.localeCompare(a.read_on));
  return (
    <section className="space-y-2" aria-label={t("util.readings")}>
      <h3 className="text-sm font-medium">{t("util.readings")}</h3>
      {!readings.data ? (
        <Skeleton className="h-10 rounded-xl" />
      ) : list.length === 0 ? (
        <p className="text-xs text-muted-foreground">{t("util.noReadings")}</p>
      ) : (
        <ul className="divide-y divide-border/60 text-sm" data-testid="reading-list">
          {list.map((r) => (
            <li key={r.id} className="flex items-center gap-2 py-1.5">
              <span className="flex-1">{shortDate(r.read_on, locale)}</span>
              <span className="tabular">
                {num(r.value, locale, 3)} {meter.unit}
              </span>
              <span className="w-16 text-right text-xs text-muted-foreground">{t(`util.source.${r.source}`)}</span>
              <Button variant="ghost" size="icon-sm" aria-label={t("common.delete")} onClick={() => remove(r.id)}>
                <Trash2 />
              </Button>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={add} className="grid grid-cols-2 items-end gap-2">
        <div className="space-y-1.5">
          <Label htmlFor={`${uid}-date`}>{t("util.date")}</Label>
          <Input id={`${uid}-date`} type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`${uid}-value`}>{t("util.reading")}</Label>
          <Input
            id={`${uid}-value`}
            inputMode="decimal"
            value={value}
            aria-invalid={value !== "" && parsed === null}
            onChange={(e) => setValue(e.target.value)}
            className="tabular text-right"
          />
        </div>
        <Button type="submit" disabled={busy || parsed === null || !date} className="col-span-2">
          <Plus /> {t("common.add")}
        </Button>
      </form>
    </section>
  );
}

function TariffsSection({ meter, onChanged }: { meter: Meter; onChanged: () => Promise<void> }) {
  const { t, locale } = useI18n();
  const uid = useId();
  const tariffs = useData(() => api.tariffs(meter.id), `tariffs:${meter.id}`);
  const [from, setFrom] = useState(today());
  const [price, setPrice] = useState("");
  const [fee, setFee] = useState("");
  const [busy, setBusy] = useState(false);
  const priceValue = parseDecimal(price);
  const feeCents = fee.trim() === "" ? 0 : parseMoney(fee);
  const valid = from !== "" && priceValue !== null && feeCents !== null && feeCents >= 0;

  async function add(event: FormEvent) {
    event.preventDefault();
    if (!valid || priceValue === null || feeCents === null) return;
    setBusy(true);
    try {
      await api.addTariff(meter.id, { valid_from: from, unit_price_ct: priceValue, base_fee_monthly_cents: feeCents });
      toast.success(t("receipt.saved"));
      setPrice("");
      setFee("");
      await Promise.all([tariffs.reload(), onChanged()]);
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    try {
      await api.deleteTariff(id);
      await Promise.all([tariffs.reload(), onChanged()]);
    } catch (error) {
      toast.error((error as Error).message);
    }
  }

  const list = [...(tariffs.data ?? [])].sort((a, b) => b.valid_from.localeCompare(a.valid_from));
  return (
    <section className="space-y-2" aria-label={t("util.tariffs")}>
      <h3 className="text-sm font-medium">{t("util.tariffs")}</h3>
      {!tariffs.data ? (
        <Skeleton className="h-10 rounded-xl" />
      ) : list.length === 0 ? (
        <p className="text-xs text-muted-foreground">{t("util.noTariffs")}</p>
      ) : (
        <ul className="divide-y divide-border/60 text-sm" data-testid="tariff-list">
          {list.map((tariff) => (
            <li key={tariff.id} className="flex items-center gap-2 py-1.5">
              <span className="w-28 shrink-0">{shortDate(tariff.valid_from, locale)}</span>
              <span className="tabular min-w-0 flex-1 text-xs text-muted-foreground">
                {t("util.tariffLine", {
                  price: num(tariff.unit_price_ct, locale, 4),
                  unit: meter.unit,
                  fee: money(tariff.base_fee_monthly_cents, locale),
                })}
              </span>
              <Button variant="ghost" size="icon-sm" aria-label={t("common.delete")} onClick={() => remove(tariff.id)}>
                <Trash2 />
              </Button>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={add} className="grid grid-cols-2 items-end gap-2">
        <div className="col-span-2 space-y-1.5">
          <Label htmlFor={`${uid}-from`}>{t("util.validFrom")}</Label>
          <Input id={`${uid}-from`} type="date" value={from} onChange={(e) => setFrom(e.target.value)} required />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`${uid}-price`}>{t("util.price", { unit: meter.unit })}</Label>
          <Input
            id={`${uid}-price`}
            inputMode="decimal"
            value={price}
            aria-invalid={price !== "" && priceValue === null}
            onChange={(e) => setPrice(e.target.value)}
            className="tabular text-right"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`${uid}-fee`}>{t("util.baseFee")}</Label>
          <Input
            id={`${uid}-fee`}
            inputMode="decimal"
            value={fee}
            aria-invalid={feeCents === null}
            onChange={(e) => setFee(e.target.value)}
            className="tabular text-right"
          />
        </div>
        <Button type="submit" disabled={busy || !valid} className="col-span-2">
          <Plus /> {t("common.add")}
        </Button>
      </form>
    </section>
  );
}

function InstalmentSection({ meter, onChanged }: { meter: Meter; onChanged: () => Promise<void> }) {
  const { t, locale } = useI18n();
  const uid = useId();
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const cents = parseMoney(amount);
  const valid = cents !== null && cents > 0;

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!valid || cents === null) return;
    setBusy(true);
    try {
      await api.createRecurring({
        name: `${meter.name} ${t("util.instalmentSuffix")}`,
        category_id: meter.category_id,
        amount_cents: cents,
        interval_months: 1,
        start_on: today(),
        end_on: null,
        meter_id: meter.id,
      });
      toast.success(t("util.instalmentCreated"));
      setAmount("");
      await onChanged();
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={create} className="grid grid-cols-2 items-end gap-2" aria-label={t("util.instalment")}>
      <div className="space-y-1.5">
        <Label htmlFor={`${uid}-amount`}>{t("util.instalment")}</Label>
        <Input
          id={`${uid}-amount`}
          inputMode="decimal"
          value={amount}
          placeholder={centsToInput(0, locale)}
          aria-invalid={amount !== "" && !valid}
          onChange={(e) => setAmount(e.target.value)}
          className="tabular text-right"
        />
      </div>
      <Button type="submit" disabled={busy || !valid}>
        {t("util.createInstalment")}
      </Button>
    </form>
  );
}

function MeterCard({
  index,
  meter,
  categories,
  version,
  onChanged,
}: {
  index: number;
  meter: Meter;
  categories: Category[];
  version: number;
  onChanged: () => Promise<void>;
}) {
  const { t, locale } = useI18n();
  const summary = useData(() => api.meterSummary(meter.id), `summary:${meter.id}:${version}`);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const Icon = KIND_ICON[meter.kind];
  const s = summary.data;

  // a change inside the card moves the summary; the list is reloaded for last_reading
  async function changed() {
    await Promise.all([summary.reload(), onChanged()]);
  }

  async function save(body: MeterBody): Promise<boolean> {
    try {
      await api.updateMeter(meter.id, body);
      toast.success(t("receipt.saved"));
      setEditing(false);
      await changed();
      return true;
    } catch (error) {
      toast.error((error as Error).message);
      return false;
    }
  }

  async function remove() {
    if (!window.confirm(t("util.deleteMeter", { name: meter.name }))) return;
    try {
      await api.deleteMeter(meter.id);
      toast.success(t("common.delete"));
      await onChanged();
    } catch (error) {
      toast.error((error as Error).message);
    }
  }

  return (
    <Tile
      index={index}
      testId="meter-card"
      title={
        <span className="flex items-center gap-2 text-foreground">
          <Icon className="size-4 text-primary" aria-hidden />
          <span className="text-base font-semibold">{meter.name}</span>
        </span>
      }
      action={
        <div className="flex gap-1">
          <Button variant="ghost" size="icon-sm" aria-label={`${t("common.edit")}: ${meter.name}`} onClick={() => setEditing((v) => !v)}>
            <Pencil />
          </Button>
          <Button variant="ghost" size="icon-sm" aria-label={`${t("common.delete")}: ${meter.name}`} onClick={remove}>
            <Trash2 />
          </Button>
        </div>
      }
    >
      <p className="-mt-2 text-xs text-muted-foreground">
        {t(`util.kind.${meter.kind}`)} · {meter.unit}
        {meter.meter_number ? ` · ${meter.meter_number}` : ""}
      </p>

      {editing && (
        <MeterForm initial={meter} categories={categories} submitLabel={t("common.save")} onSubmit={save} onCancel={() => setEditing(false)} />
      )}

      {summary.error ? (
        <p className="text-sm text-destructive">{summary.error.message}</p>
      ) : !s ? (
        <Skeleton className="h-32 rounded-xl" />
      ) : (
        <>
          <p className="text-xs text-muted-foreground">
            {t("util.period", { start: shortDate(s.period_start, locale), end: shortDate(s.period_end, locale) })}
          </p>
          <div className="rounded-2xl bg-muted/40 p-3">
            {s.projected_balance_cents !== null ? (
              <Balance cents={s.projected_balance_cents} testId="forecast" className="text-2xl" />
            ) : (
              <p className="text-xs text-muted-foreground">
                {t(s.per_day === null ? "util.noForecastReadings" : s.projected_cost_cents === null ? "util.noForecastTariff" : "util.noForecastInstalment")}
              </p>
            )}
            {s.suggested_instalment_cents !== null && (
              <p className="tabular mt-1 text-xs text-muted-foreground">
                {t("util.suggested", { amount: money(s.suggested_instalment_cents, locale) })}
              </p>
            )}
          </div>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2" data-testid="meter-stats">
            <Stat label={t("util.consumption")} value={`${num(s.consumption, locale)} ${meter.unit}`} />
            <Stat label={t("util.perDay")} value={s.per_day === null ? "–" : `${num(s.per_day, locale)} ${meter.unit}`} />
            <Stat
              label={t("util.projected")}
              value={s.projected_consumption === null ? "–" : `${num(s.projected_consumption, locale, 0)} ${meter.unit}`}
            />
            <Stat label={t("util.projectedCost")} value={s.projected_cost_cents === null ? "–" : money(s.projected_cost_cents, locale)} />
            <Stat label={t("util.paid")} value={money(s.paid_cents, locale)} />
          </dl>
          {s.intervals.length > 0 && <IntervalChart summary={s} unit={meter.unit} />}
        </>
      )}

      <Button variant="outline" size="sm" aria-expanded={open} onClick={() => setOpen((v) => !v)} className="self-start">
        {open ? <ChevronDown /> : <ChevronRight />} {t("util.details")}
      </Button>
      {open && (
        <div className="space-y-5 border-t border-border/60 pt-3">
          <ReadingsSection meter={meter} onChanged={changed} />
          <TariffsSection meter={meter} onChanged={changed} />
          <InstalmentSection meter={meter} onChanged={changed} />
        </div>
      )}
    </Tile>
  );
}

/* ---------- bills ---------- */

function BillRow({
  bill,
  meters,
  onReload,
  onApplied,
}: {
  bill: UtilityBill;
  meters: Meter[];
  onReload: () => Promise<void>;
  onApplied: () => Promise<void>;
}) {
  const { t, locale } = useI18n();
  const uid = useId();
  const [busy, setBusy] = useState(false);
  const Icon = KIND_ICON[bill.kind];
  const unit = bill.unit ? ` ${bill.unit}` : "";

  async function run(action: () => Promise<void>) {
    setBusy(true);
    try {
      await action();
    } catch (error) {
      toast.error(apiMessage(error, t));
    } finally {
      setBusy(false);
    }
  }

  const assign = (value: string) =>
    run(async () => {
      await api.assignBill(bill.id, value ? Number(value) : null);
      await onReload();
    });

  const apply = () =>
    run(async () => {
      const result = await api.applyBill(bill.id);
      const key: MessageKey = result.tariff && result.instalment ? "util.applied.both" : result.tariff ? "util.applied.tariff" : result.instalment ? "util.applied.instalment" : "util.applied.none";
      toast.success(t(key));
      await onApplied();
    });

  const remove = () => {
    if (!window.confirm(t("util.deleteBill", { name: bill.provider || bill.file_name }))) return;
    return run(async () => {
      await api.deleteBill(bill.id);
      await onReload();
    });
  };

  const error = bill.error === "not_a_bill" ? t("util.billError.not_a_bill") : bill.error;
  return (
    <li data-testid="bill-row" className="space-y-2 py-3 text-sm">
      <div className="flex items-start gap-2">
        <Icon className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium">{bill.provider || bill.file_name}</p>
          <p className="text-xs text-muted-foreground">
            {t(`util.kind.${bill.kind}`)}
            {bill.period_start && bill.period_end ? ` · ${shortDate(bill.period_start, locale)} – ${shortDate(bill.period_end, locale)}` : ""}
          </p>
        </div>
        <a
          href={api.billFileUrl(bill.id)}
          target="_blank"
          rel="noopener"
          aria-label={`${t("util.file")}: ${bill.file_name}`}
          className="inline-flex size-7 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground"
        >
          <ExternalLink className="size-4" />
        </a>
        <Button variant="ghost" size="icon-sm" aria-label={`${t("common.delete")}: ${bill.provider || bill.file_name}`} disabled={busy} onClick={remove}>
          <Trash2 />
        </Button>
      </div>

      {error ? (
        <p className="text-sm text-destructive">{error}</p>
      ) : (
        <>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
            {bill.consumption !== null && <Stat label={t("util.consumption")} value={`${num(bill.consumption, locale)}${unit}`} />}
            {bill.total_cents !== null && <Stat label={t("util.total")} value={money(bill.total_cents, locale)} />}
            {bill.paid_cents !== null && <Stat label={t("util.paid")} value={money(bill.paid_cents, locale)} />}
            {bill.new_instalment_cents !== null && <Stat label={t("util.newInstalment")} value={money(bill.new_instalment_cents, locale)} />}
          </dl>
          {bill.balance_cents !== null && (
            <p>
              <Balance cents={bill.balance_cents} />
            </p>
          )}
        </>
      )}

      <div className="grid items-end gap-2 sm:grid-cols-[1fr_auto]">
        <div className="space-y-1.5">
          <Label htmlFor={`${uid}-meter`}>{t("util.assign")}</Label>
          <select id={`${uid}-meter`} value={bill.meter_id ?? ""} disabled={busy} onChange={(e) => assign(e.target.value)} className={SELECT_CLASS}>
            <option value="">{t("util.unassigned")}</option>
            {meters.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </div>
        <Button onClick={apply} disabled={busy || bill.meter_id === null || Boolean(bill.error)}>
          {t("util.apply")}
        </Button>
      </div>
    </li>
  );
}

/* ---------- page ---------- */

export function Utilities() {
  const { t, locale } = useI18n();
  const meters = useData(() => api.meters(), "meters");
  const categories = useData(() => api.categories(), "categories");
  const bills = useData(() => api.bills(), "bills");
  const [version, setVersion] = useState(0);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [reading, setReading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const photoInput = useRef<HTMLInputElement>(null);
  const billInput = useRef<HTMLInputElement>(null);

  if (meters.error) return <p className="glass rounded-2xl p-6 text-destructive">{meters.error.message}</p>;
  if (!meters.data || !categories.data) return <Skeleton className="h-96 rounded-3xl" />;
  const list = meters.data;
  const cats = categories.data;

  const reloadMeters = async () => {
    await meters.reload();
  };

  async function onPhoto(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setReading(true);
    try {
      const photo = await api.readMeterPhoto(file);
      const known = list.some((m) => m.id === photo.meter_id);
      setProposal({
        photo,
        meterId: known && photo.meter_id !== null ? String(photo.meter_id) : "",
        readOn: photo.read_on,
        value: decimalToInput(photo.value, locale),
      });
    } catch (error) {
      toast.error(apiMessage(error, t));
    } finally {
      setReading(false);
    }
  }

  async function onBill(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      const bill = await api.uploadBill(file);
      if (bill.error) toast.error(bill.error === "not_a_bill" ? t("util.billError.not_a_bill") : bill.error);
      else toast.success(t("util.billUploaded"));
      await bills.reload();
    } catch (error) {
      toast.error(apiMessage(error, t));
    } finally {
      setUploading(false);
    }
  }

  async function addMeter(body: MeterBody): Promise<boolean> {
    try {
      await api.createMeter(body);
      toast.success(t("receipt.saved"));
      await meters.reload();
      return true;
    } catch (error) {
      toast.error((error as Error).message);
      return false;
    }
  }

  async function billApplied() {
    setVersion((v) => v + 1);
    await meters.reload();
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">{t("nav.utilities")}</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{t("util.hint")}</p>
        </div>
        <Link href="/fixed" className="inline-flex items-center gap-1 text-sm text-primary hover:underline">
          {t("nav.fixed")} <ChevronRight className="size-4" />
        </Link>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button onClick={() => photoInput.current?.click()} disabled={reading}>
          <Camera /> {t("util.photo")}
        </Button>
        <Button variant="outline" onClick={() => billInput.current?.click()} disabled={uploading}>
          <Upload /> {t("util.uploadBill")}
        </Button>
        <input ref={photoInput} type="file" accept="image/*" capture="environment" hidden data-testid="meter-photo-input" onChange={onPhoto} />
        <input ref={billInput} type="file" accept="application/pdf,image/*" hidden data-testid="bill-input" onChange={onBill} />
      </div>

      {proposal && (
        <PhotoConfirm
          proposal={proposal}
          meters={list}
          onChange={setProposal}
          onCancel={() => setProposal(null)}
          onSaved={async () => {
            setProposal(null);
            setVersion((v) => v + 1);
            await meters.reload();
          }}
        />
      )}

      {list.length === 0 ? (
        <p className="glass rounded-2xl p-6 text-center text-sm text-muted-foreground">{t("util.noMeters")}</p>
      ) : (
        <div className="grid items-start gap-4 lg:grid-cols-2">
          {list.map((meter, i) => (
            <MeterCard key={meter.id} index={i + 1} meter={meter} categories={cats} version={version} onChanged={reloadMeters} />
          ))}
        </div>
      )}

      <Tile index={list.length + 1} title={t("util.addMeter")}>
        <MeterForm categories={cats} submitLabel={t("common.add")} onSubmit={addMeter} />
      </Tile>

      <Tile index={list.length + 2} title={t("util.bills")}>
        {!bills.data ? (
          <Skeleton className="h-20 rounded-xl" />
        ) : bills.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("util.noBills")}</p>
        ) : (
          <ul className="divide-y divide-border/60">
            {bills.data.map((bill) => (
              <BillRow key={bill.id} bill={bill} meters={list} onReload={() => bills.reload()} onApplied={billApplied} />
            ))}
          </ul>
        )}
      </Tile>
    </div>
  );
}
