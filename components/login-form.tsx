"use client";

import { motion } from "motion/react";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useI18n } from "@/lib/i18n/provider";
import { errorFrom } from "@/lib/api";
import { MIN_LENGTH, isPasswordProblem, problemMessage } from "@/lib/password";
import { safeNext } from "@/lib/safe-next";

export function LoginForm() {
  const { t, locale, setLocale } = useI18n();
  const params = useSearchParams();
  const [signup, setSignup] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch("/api/v1/setup")
      .then((r) => r.json())
      .then((state) => setSignup(Boolean(state.needs_first_user)))
      .catch(() => undefined);
  }, []);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    const response = await fetch(signup ? "/api/auth/signup" : "/api/auth/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(Object.fromEntries(form)),
    }).catch(() => null);
    if (response?.ok) {
      const body = await response.json().catch(() => ({}));
      // the operator has its own page (no household)
      const next = body.is_operator ? "/operator" : safeNext(params.get("next"));
      // a one-time password has to be replaced first
      window.location.href = body.must_change_password ? `/password?next=${encodeURIComponent(next)}` : next;
      return;
    }
    setBusy(false);
    if (!response) return setError(t("auth.failed"));
    if (response.status === 429) return setError(t("auth.tooMany"));
    const error = errorFrom(response.status, await response.json().catch(() => ({})), response.statusText);
    if (error.message === "account_disabled") return setError(t("auth.disabled"));
    const reasons = error.reasons.filter(isPasswordProblem);
    if (reasons.length) return setError(reasons.map((r) => t(problemMessage(r))).join(" "));
    setError(signup ? error.message : t("auth.failed"));
  }

  return (
    <motion.form
      onSubmit={submit}
      initial={{ opacity: 0, y: 20, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.5, ease: [0.2, 0.8, 0.2, 1] }}
      className="glass flex w-full max-w-sm flex-col gap-5 rounded-3xl p-8"
    >
      <div className="flex items-start justify-between">
        <div className="space-y-1">
          <div className="mb-3 size-11 rounded-2xl bg-gradient-to-br from-primary to-chart-4 shadow-lg shadow-primary/30" aria-hidden />
          <h1 className="text-gradient text-3xl font-semibold tracking-tight">{t("app.name")}</h1>
          <p className="text-sm text-muted-foreground">{signup ? t("auth.signupHint") : t("app.tagline")}</p>
        </div>
        <Button type="button" variant="ghost" size="sm" className="uppercase" onClick={() => setLocale(locale === "de" ? "en" : "de")}>
          {locale === "de" ? "en" : "de"}
        </Button>
      </div>
      <div className="space-y-2">
        <Label htmlFor="username">{t("auth.username")}</Label>
        <Input id="username" name="username" autoComplete="username" required autoFocus className="h-10" />
      </div>
      {signup && (
        <div className="space-y-2">
          <Label htmlFor="display_name">{t("auth.displayName")}</Label>
          <Input id="display_name" name="display_name" autoComplete="name" className="h-10" />
        </div>
      )}
      <div className="space-y-2">
        <Label htmlFor="password">{t("auth.password")}</Label>
        <Input
          id="password"
          name="password"
          type="password"
          autoComplete={signup ? "new-password" : "current-password"}
          minLength={signup ? MIN_LENGTH : undefined}
          aria-describedby={signup ? "password-rules" : undefined}
          required
          className="h-10"
        />
        {signup && (
          <p id="password-rules" className="text-xs text-muted-foreground">
            {t("password.rules")}
          </p>
        )}
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <Button type="submit" size="lg" disabled={busy} className="h-11 bg-gradient-to-r from-primary to-chart-4 text-base">
        {signup ? t("auth.signup") : t("auth.login")}
      </Button>
    </motion.form>
  );
}
