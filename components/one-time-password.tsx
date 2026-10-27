"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n/provider";

// Shown once after adding a member or a household or resetting a password.
export function OneTimePasswordPanel({ name, password, onDone }: { name: string; password: string; onDone: () => void }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  return (
    <div role="status" className="space-y-2 rounded-xl border-2 border-primary p-3" data-testid="one-time-password">
      <p className="text-sm font-medium">{t("members.oneTimeTitle", { name })}</p>
      <p className="break-all font-mono text-lg tracking-wide select-all">{password}</p>
      <p className="text-xs text-muted-foreground">{t("members.oneTimeHint")}</p>
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() =>
            void navigator.clipboard
              ?.writeText(password)
              .then(() => setCopied(true))
              .catch(() => undefined)
          }
        >
          {copied ? <Check /> : <Copy />} {copied ? t("members.copied") : t("members.copy")}
        </Button>
        <Button type="button" size="sm" onClick={onDone}>
          {t("members.done")}
        </Button>
      </div>
    </div>
  );
}
