"use client";

import { useId, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { errorFrom } from "@/lib/api";
import { useI18n } from "@/lib/i18n/provider";
import { MAX_LENGTH, isPasswordProblem, localProblems, problemMessage, type PasswordProblem } from "@/lib/password";

// Own password change, also the way out of a one-time password (forced).
// Goes through app/api/auth/password, which sets the new session cookie.
export function PasswordForm({ forced = false, onDone }: { forced?: boolean; onDone?: () => void }) {
  const { t } = useI18n();
  const id = useId();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const local = localProblems(next, confirm);
  // hints while typing only once something is there, so nobody is scolded early
  const hints = next === "" ? [] : local;
  const ready = current !== "" && next !== "" && confirm !== "" && local.length === 0;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!ready) return;
    setBusy(true);
    setErrors([]);
    const response = await fetch("/api/auth/password", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ current_password: current, new_password: next }),
    }).catch(() => null);
    setBusy(false);
    if (response?.ok) {
      setCurrent("");
      setNext("");
      setConfirm("");
      toast.success(t("password.changed"));
      onDone?.();
      return;
    }
    if (!response) return setErrors([t("auth.failed")]);
    if (response.status === 429) return setErrors([t("auth.tooMany")]);
    const error = errorFrom(response.status, await response.json().catch(() => ({})), response.statusText);
    if (error.message === "wrong_current_password") return setErrors([t("password.wrongCurrent")]);
    const reasons = error.reasons.filter(isPasswordProblem);
    setErrors(reasons.length ? reasons.map((r) => t(problemMessage(r))) : [error.message]);
  }

  const field = (name: string, label: string, value: string, set: (v: string) => void, autoComplete: string, extra = {}) => (
    <div className="space-y-1.5">
      <Label htmlFor={`${id}-${name}`}>{label}</Label>
      <Input
        id={`${id}-${name}`}
        type={show ? "text" : "password"}
        autoComplete={autoComplete}
        maxLength={MAX_LENGTH * 2}
        value={value}
        onChange={(e) => set(e.target.value)}
        {...extra}
      />
    </div>
  );

  return (
    <form onSubmit={submit} className="space-y-3" data-testid="password-form">
      {forced && <p className="text-sm">{t("password.forcedHint")}</p>}
      {field("current", forced ? t("password.oneTime") : t("password.current"), current, setCurrent, "current-password")}
      {field("new", t("password.new"), next, setNext, "new-password", {
        "aria-describedby": `${id}-rules ${id}-hints`,
        "aria-invalid": hints.includes("too_short") || hints.includes("too_long"),
      })}
      <p id={`${id}-rules`} className="text-xs text-muted-foreground">
        {t("password.rules")}
      </p>
      {field("confirm", t("password.confirm"), confirm, setConfirm, "new-password", {
        "aria-describedby": `${id}-hints`,
        "aria-invalid": hints.includes("mismatch"),
      })}
      <ul id={`${id}-hints`} aria-live="polite" className="space-y-0.5 text-xs text-muted-foreground">
        {hints.map((problem: PasswordProblem) => (
          <li key={problem}>{t(problemMessage(problem))}</li>
        ))}
      </ul>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)} className="size-4 accent-primary" />
        {t("password.show")}
      </label>
      {errors.length > 0 && (
        <ul role="alert" className="space-y-0.5 text-sm text-destructive">
          {errors.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      )}
      <Button type="submit" disabled={busy || !ready}>
        {t("password.submit")}
      </Button>
    </form>
  );
}
