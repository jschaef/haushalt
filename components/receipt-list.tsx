"use client";

import { animate, motion, useMotionValue, useTransform } from "motion/react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, ViewTransition } from "react";
import { AlertTriangle, Camera, FileText, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";
import { useScan } from "@/components/scan";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type Receipt } from "@/lib/api";
import { money, shortDate } from "@/lib/format";
import { haptic, useData } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";

type Filter = "all" | "draft" | "confirmed";

function Dropzone() {
  const { t } = useI18n();
  const { upload, openCamera, openFiles, busy } = useScan();
  const [over, setOver] = useState(false);
  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(event) => {
        event.preventDefault();
        setOver(false);
        void upload(Array.from(event.dataTransfer.files));
      }}
      className={cn(
        "glass flex flex-col items-center gap-3 rounded-3xl border-2 border-dashed p-6 text-center transition-colors",
        over && "border-primary bg-primary/10",
      )}
      data-testid="dropzone"
    >
      <div className="flex size-12 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-chart-4 text-primary-foreground">
        <Upload className="size-5" />
      </div>
      <div>
        <p className="font-medium">{t("receipts.drop")}</p>
        <p className="text-sm text-muted-foreground">{t("receipts.dropHint")}</p>
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        <Button onClick={openCamera} disabled={busy}>
          <Camera /> {t("receipts.camera")}
        </Button>
        <Button variant="outline" onClick={openFiles} disabled={busy}>
          {t("receipts.choose")}
        </Button>
      </div>
    </div>
  );
}

// Swipe left on a phone to delete; a tap opens the receipt.
function SwipeRow({ receipt, onDelete }: { receipt: Receipt; onDelete: (r: Receipt) => void }) {
  const { t, locale } = useI18n();
  const x = useMotionValue(0);
  const reveal = useTransform(x, [-120, -40, 0], [1, 0.4, 0]);
  return (
    <li className="relative overflow-hidden rounded-2xl">
      <motion.div style={{ opacity: reveal }} className="absolute inset-0 flex items-center justify-end rounded-2xl bg-destructive/80 pr-6 text-white">
        <Trash2 className="size-5" />
      </motion.div>
      <motion.div
        drag="x"
        dragDirectionLock
        dragConstraints={{ left: -160, right: 0 }}
        dragElastic={0.1}
        style={{ x }}
        onDragEnd={(_, info) => {
          if (info.offset.x < -110) {
            haptic(20);
            onDelete(receipt);
          } else {
            void animate(x, 0, { type: "spring", stiffness: 500, damping: 40 });
          }
        }}
        className="relative"
      >
        <ViewTransition name={`receipt-${receipt.id}`} share="morph">
          <Link
            href={`/receipts/${receipt.id}`}
            draggable={false}
            className="glass flex items-center gap-3 rounded-2xl p-3 transition-colors hover:bg-accent/40"
            data-testid="receipt-row"
          >
            <div className="flex size-11 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-muted">
              {receipt.source === "pdf" ? (
                <FileText className="size-5 text-muted-foreground" />
              ) : (
                // eslint-disable-next-line @next/next/no-img-element -- authenticated API image, not optimizable
                <img src={api.fileUrl(receipt.id)} alt="" loading="lazy" className="size-full object-cover" draggable={false} />
              )}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate font-medium">{receipt.store_name || t("receipts.unknownStore")}</div>
              <div className="text-xs text-muted-foreground">
                {receipt.purchased_on ? shortDate(receipt.purchased_on, locale) : t("receipts.noDate")} · {receipt.items.length} {t("receipt.items")}
              </div>
            </div>
            <div className="flex flex-col items-end gap-1">
              <span className="tabular font-semibold">{money(receipt.total_cents, locale, receipt.currency)}</span>
              {receipt.error ? (
                <Badge variant="destructive">
                  <AlertTriangle /> {t("receipts.error")}
                </Badge>
              ) : receipt.status === "draft" ? (
                <Badge variant="secondary">{t("receipts.draft")}</Badge>
              ) : null}
            </div>
          </Link>
        </ViewTransition>
      </motion.div>
    </li>
  );
}

export function ReceiptList() {
  const { t } = useI18n();
  const params = useSearchParams();
  const router = useRouter();
  const { version } = useScan();
  const initial = (params.get("status") as Filter) || "all";
  const [filter, setFilter] = useState<Filter>(["draft", "confirmed"].includes(initial) ? initial : "all");
  const store = params.get("store");
  const receipts = useData(() => api.receipts(filter === "all" ? undefined : filter), `${filter}:${version}`);
  const { openCamera } = useScan();

  // the PWA shortcut "Scan receipt" opens /receipts?scan=1
  useEffect(() => {
    if (params.get("scan") === "1") {
      router.replace("/receipts");
      openCamera();
    }
  }, [params, router, openCamera]);

  const remove = async (receipt: Receipt) => {
    receipts.setData((list) => list?.filter((r) => r.id !== receipt.id) ?? null);
    try {
      await api.deleteReceipt(receipt.id);
      toast.success(t("receipts.deleted"));
    } catch (error) {
      toast.error((error as Error).message);
      void receipts.reload();
    }
  };

  const visible = (receipts.data ?? []).filter((r) => !store || r.store_name === store);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
          {t("receipts.title")}
          {store && <span className="text-muted-foreground"> · {store}</span>}
        </h1>
        <div className="glass flex gap-1 rounded-xl p-1" role="tablist">
          {(["all", "draft", "confirmed"] as Filter[]).map((value) => (
            <button
              key={value}
              role="tab"
              aria-selected={filter === value}
              onClick={() => setFilter(value)}
              className={cn("rounded-lg px-3 py-1.5 text-xs font-medium text-muted-foreground", filter === value && "bg-primary text-primary-foreground")}
            >
              {t(value === "all" ? "receipts.all" : value === "draft" ? "receipts.drafts" : "receipts.confirmed")}
            </button>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[22rem_minmax(0,1fr)]">
        <div className="lg:sticky lg:top-24 lg:self-start">
          <Dropzone />
        </div>
        <div>
          {receipts.loading && !receipts.data ? (
            <div className="space-y-2">
              {[...Array(4)].map((_, i) => (
                <Skeleton key={i} className="h-16 rounded-2xl" />
              ))}
            </div>
          ) : visible.length === 0 ? (
            <p className="glass rounded-2xl p-6 text-center text-muted-foreground">{t("receipts.empty")}</p>
          ) : (
            <>
              <p className="mb-2 text-xs text-muted-foreground md:hidden">{t("receipts.swipeHint")}</p>
              <ul className="space-y-2">
                {visible.map((receipt) => (
                  <SwipeRow key={receipt.id} receipt={receipt} onDelete={remove} />
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
