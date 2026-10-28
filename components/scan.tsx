"use client";

import { useRouter } from "next/navigation";
import { createContext, use, useCallback, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { api, type Receipt } from "@/lib/api";
import { haptic } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n/provider";

type Scan = {
  // opens the camera (phones) or the file picker
  openCamera: () => void;
  openFiles: () => void;
  upload: (files: File[]) => Promise<Receipt[]>;
  busy: boolean;
  // bumped after every upload, lists reload on change
  version: number;
};

const ScanContext = createContext<Scan | null>(null);

const ACCEPT = "image/jpeg,image/png,image/webp,image/gif,application/pdf";

export function ScanProvider({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const router = useRouter();
  const camera = useRef<HTMLInputElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState(0);

  const upload = useCallback(
    async (files: File[]) => {
      if (!files.length) return [];
      setBusy(true);
      const pending = toast.loading(t("receipts.reading", { count: files.length }));
      try {
        const created = await api.upload(files);
        haptic([10, 40, 10]);
        // a receipt recorded before comes back as the existing one, not anew
        const present = created.filter((r) => r.already_present).length;
        if (present === created.length) toast.info(t("receipts.alreadyPresent", { count: present }), { id: pending });
        else {
          toast.success(t("receipts.read", { count: created.length - present }), { id: pending });
          if (present) toast.info(t("receipts.alreadyPresent", { count: present }));
        }
        setVersion((v) => v + 1);
        // a single receipt goes straight to its review
        if (created.length === 1) router.push(`/receipts/${created[0].id}`);
        return created;
      } catch (error) {
        toast.error((error as Error).message || t("common.error"), { id: pending });
        return [];
      } finally {
        setBusy(false);
      }
    },
    [router, t],
  );

  const onChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    void upload(files);
  };

  return (
    <ScanContext
      value={{
        openCamera: () => camera.current?.click(),
        openFiles: () => picker.current?.click(),
        upload,
        busy,
        version,
      }}
    >
      {children}
      <input ref={camera} type="file" accept="image/*" capture="environment" hidden onChange={onChange} data-testid="camera-input" />
      <input ref={picker} type="file" accept={ACCEPT} multiple hidden onChange={onChange} data-testid="file-input" />
    </ScanContext>
  );
}

export function useScan(): Scan {
  const context = use(ScanContext);
  if (!context) throw new Error("useScan outside ScanProvider");
  return context;
}
