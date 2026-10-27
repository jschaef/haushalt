"use client";

import { useState, type FormEvent } from "react";
import { KeyRound, LogOut, Plus } from "lucide-react";
import { toast } from "sonner";
import { OneTimePasswordPanel } from "@/components/one-time-password";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type OperatorHousehold } from "@/lib/api";
import { shortDate } from "@/lib/format";
import { useData } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n/provider";

type Shown = { name: string; password: string };

async function logout() {
  await fetch("/api/auth/logout", { method: "POST" });
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  window.location.href = "/login";
}

function HouseholdRow({ household, onChanged, onOneTime }: { household: OperatorHousehold; onChanged: () => void; onOneTime: (s: Shown) => void }) {
  const { t, locale } = useI18n();
  const [name, setName] = useState(household.name);
  const [busy, setBusy] = useState(false);
  const uid = `household-${household.id}`;

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    try {
      await action();
      onChanged();
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="glass space-y-3 rounded-2xl p-4" data-testid="household-row">
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-40 flex-1 space-y-1">
          <Label htmlFor={`${uid}-name`} className="text-xs">
            {t("operator.name")}
          </Label>
          <Input id={`${uid}-name`} value={name} maxLength={64} onChange={(e) => setName(e.target.value)} />
        </div>
        <Button
          variant="outline"
          disabled={busy || !name.trim() || name.trim() === household.name}
          onClick={() => void run(() => api.operator.update(household.id, { name }))}
        >
          {t("common.save")}
        </Button>
        <Button
          variant={household.disabled ? "default" : "outline"}
          disabled={busy}
          onClick={() => void run(() => api.operator.update(household.id, { disabled: !household.disabled }))}
        >
          {household.disabled ? t("operator.enable") : t("operator.disable")}
        </Button>
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
        {household.disabled && <Badge variant="destructive">{t("operator.disabled")}</Badge>}
        <span>{t("operator.members", { n: household.members })}</span>
        <span>{t("operator.since", { date: shortDate(household.created_at.slice(0, 10), locale) })}</span>
      </div>
      <ul className="space-y-1.5">
        {household.admins.map((admin) => (
          <li key={admin.id} className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium">{admin.display_name}</span>
            <span className="text-muted-foreground">({admin.username})</span>
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  if (!window.confirm(t("operator.confirmReset", { name: admin.display_name }))) return;
                  const { one_time_password } = await api.operator.resetAdmin(admin.id);
                  onOneTime({ name: admin.display_name, password: one_time_password });
                })
              }
            >
              <KeyRound /> {t("operator.resetAdmin")}
            </Button>
          </li>
        ))}
      </ul>
    </li>
  );
}

function NewHousehold({ onCreated }: { onCreated: (s: Shown) => void }) {
  const { t } = useI18n();
  const [name, setName] = useState("");
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const created = await api.operator.create({ name, admin_username: username.trim(), admin_display_name: displayName.trim() });
      onCreated({ name: created.household.admins[0]?.display_name ?? username, password: created.one_time_password });
      setName("");
      setUsername("");
      setDisplayName("");
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="glass space-y-3 rounded-2xl p-4" data-testid="new-household">
      <h2 className="font-semibold">{t("operator.add")}</h2>
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="space-y-1">
          <Label htmlFor="new-household-name">{t("operator.name")}</Label>
          <Input id="new-household-name" value={name} maxLength={64} onChange={(e) => setName(e.target.value)} required />
        </div>
        <div className="space-y-1">
          <Label htmlFor="new-household-admin">{t("operator.adminUsername")}</Label>
          <Input
            id="new-household-admin"
            value={username}
            maxLength={64}
            autoCapitalize="none"
            spellCheck={false}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="new-household-display">{t("operator.adminName")}</Label>
          <Input id="new-household-display" value={displayName} maxLength={128} onChange={(e) => setDisplayName(e.target.value)} />
        </div>
      </div>
      <p className="text-xs text-muted-foreground">{t("operator.addHint")}</p>
      <Button type="submit" disabled={busy || !name.trim() || !username.trim()}>
        <Plus /> {t("operator.addButton")}
      </Button>
    </form>
  );
}

export function Operator() {
  const { t } = useI18n();
  const households = useData(() => api.operator.households(), "operator-households");
  const [shown, setShown] = useState<Shown | null>(null);
  const reload = () => void households.reload();

  return (
    <main className="mx-auto max-w-4xl space-y-4 p-4 md:p-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("operator.title")}</h1>
          <p className="text-sm text-muted-foreground">{t("operator.hint")}</p>
        </div>
        <Button variant="outline" onClick={() => void logout()}>
          <LogOut /> {t("nav.logout")}
        </Button>
      </header>
      {shown && <OneTimePasswordPanel name={shown.name} password={shown.password} onDone={() => setShown(null)} />}
      <NewHousehold
        onCreated={(s) => {
          setShown(s);
          reload();
        }}
      />
      <section aria-labelledby="households-title" className="space-y-2">
        <h2 id="households-title" className="font-semibold">
          {t("operator.households")}
        </h2>
        {!households.data ? (
          <Skeleton className="h-32 rounded-2xl" />
        ) : (
          <ul className="space-y-3">
            {households.data.map((h) => (
              <HouseholdRow key={`${h.id}:${h.name}:${h.disabled}`} household={h} onChanged={reload} onOneTime={setShown} />
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
