"use client";

import { useSearchParams } from "next/navigation";
import { PasswordForm } from "@/components/password-form";
import { useI18n } from "@/lib/i18n/provider";
import { safeNext } from "@/lib/safe-next";

export function ForcedPassword() {
  const { t } = useI18n();
  const params = useSearchParams();
  return (
    <section className="glass w-full max-w-sm space-y-4 rounded-3xl p-8">
      <h1 className="text-2xl font-semibold tracking-tight">{t("password.title")}</h1>
      <PasswordForm forced onDone={() => (window.location.href = safeNext(params.get("next")))} />
    </section>
  );
}
