"use client";

import { useEffect, useId, useState, type FormEvent } from "react";
import { useTheme } from "next-themes";
import { Check, Copy, KeyRound, Plus, ShieldCheck, Trash2, UserCheck, UserX } from "lucide-react";
import { toast } from "sonner";
import { Tile } from "@/components/bento";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { OneTimePasswordPanel } from "@/components/one-time-password";
import { PasswordForm } from "@/components/password-form";
import {
  api,
  spendingCategories,
  type ApiToken,
  type BankAccount,
  type BankAccountInput,
  type Category,
  type Merchant,
  type NewApiToken,
  type OneTimePassword,
  type Tag,
  type User,
} from "@/lib/api";
import { KEY_RE, effectiveKey, toCategoryKey } from "@/lib/category-key";
import { dateTime, localToday, shortDate } from "@/lib/format";
import { useData } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n/provider";
import type { Locale, MessageKey } from "@/lib/i18n/messages";
import type { Theme } from "@/lib/themes";
import { cn } from "@/lib/utils";

const SELECT_CLASS =
  "h-8 w-full appearance-none rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50 dark:bg-input/30";
const COLOR_CLASS = "h-8 w-10 shrink-0 cursor-pointer rounded-lg border border-input bg-transparent p-0.5";

type CategoryBody = Omit<Category, "id">;

function Segment({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <Button variant={active ? "default" : "outline"} size="sm" aria-pressed={active} onClick={onClick}>
      {children}
    </Button>
  );
}

function LanguageTile() {
  const { t, locale, setLocale } = useI18n();
  const choose = (next: Locale) => {
    if (next === locale) return;
    setLocale(next);
    void api.updateMe({ locale: next }).catch(() => undefined);
  };
  return (
    <Tile index={0} title={t("settings.language")}>
      <div className="flex gap-2">
        <Segment active={locale === "de"} onClick={() => choose("de")}>
          DE
        </Segment>
        <Segment active={locale === "en"} onClick={() => choose("en")}>
          EN
        </Segment>
      </div>
    </Tile>
  );
}

function ThemeTile() {
  const { t } = useI18n();
  const { theme, setTheme } = useTheme();
  // next-themes knows the stored theme only on the client
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- avoid a hydration mismatch
    setMounted(true);
  }, []);
  const options: { value: Theme | "system"; label: MessageKey }[] = [
    { value: "dark", label: "settings.themeDark" },
    { value: "light", label: "settings.themeLight" },
    { value: "system", label: "settings.themeSystem" },
    { value: "contrast", label: "settings.themeContrast" },
    { value: "contrast-light", label: "settings.themeContrastLight" },
  ];
  return (
    <Tile index={1} title={t("settings.theme")}>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => (
          <Segment key={option.value} active={mounted && theme === option.value} onClick={() => setTheme(option.value)}>
            {t(option.label)}
          </Segment>
        ))}
      </div>
    </Tile>
  );
}

function HouseholdTile() {
  const { t } = useI18n();
  const me = useData(() => api.me(), "me");
  const household = useData(() => api.household(), "household");
  const [name, setName] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const value = name ?? household.data?.name ?? "";

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      household.setData(await api.renameHousehold(value));
      setName(null);
      toast.success(t("receipt.saved"));
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Tile index={11} title={t("household.title")} testId="household-tile">
      {!household.data || !me.data ? (
        <Skeleton className="h-20 rounded-xl" />
      ) : me.data.is_admin ? (
        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="household-name">{t("household.name")}</Label>
            <Input id="household-name" value={value} maxLength={64} onChange={(e) => setName(e.target.value)} required />
          </div>
          <Button type="submit" disabled={busy || !value.trim()}>
            {t("common.save")}
          </Button>
        </form>
      ) : (
        <p className="text-sm" data-testid="household-name">
          {household.data.name}
        </p>
      )}
      <p className="mt-2 text-xs text-muted-foreground">{t("household.hint")}</p>
    </Tile>
  );
}

function ProfileTile() {
  const { t } = useI18n();
  const me = useData(() => api.me(), "me");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const loaded = me.data;

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- editable copy of the loaded profile
    if (loaded) setName(loaded.display_name);
  }, [loaded]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    try {
      me.setData(await api.updateMe({ display_name: name.trim() }));
      toast.success(t("receipt.saved"));
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Tile index={2} title={t("settings.profile")}>
      {!loaded ? (
        <Skeleton className="h-28 rounded-xl" />
      ) : (
        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="profile-name">{t("auth.displayName")}</Label>
            <Input id="profile-name" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <Button type="submit" disabled={busy || !name.trim()}>
            {t("common.save")}
          </Button>
        </form>
      )}
    </Tile>
  );
}

function PasswordTile() {
  const { t } = useI18n();
  return (
    <Tile index={3} title={t("password.title")}>
      <PasswordForm />
    </Tile>
  );
}

function MemberRow({ user, me, onChanged, onOneTime }: { user: User; me: User; onChanged: () => void; onOneTime: (v: OneTimePassword) => void }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const self = user.id === me.id;

  async function run(action: () => Promise<unknown>, question?: string) {
    if (question && !window.confirm(question)) return;
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
    <li className="space-y-2 rounded-xl bg-muted/40 px-3 py-2 text-sm" data-testid="member">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="font-medium">{user.display_name}</span>
        <span className="text-xs text-muted-foreground">@{user.username}</span>
        {self && <Badge variant="outline">{t("members.you")}</Badge>}
        {user.is_admin && <Badge>{t("members.admin")}</Badge>}
        {user.disabled && <Badge variant="destructive">{t("members.disabled")}</Badge>}
        {user.must_change_password && <Badge variant="secondary">{t("members.mustChange")}</Badge>}
      </div>
      {me.is_admin && !self && (
        <div className="flex flex-wrap gap-2" role="group" aria-label={t("members.actions", { name: user.display_name })}>
          <Button
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() =>
              void run(
                async () => onOneTime(await api.resetPassword(user.id)),
                t("members.resetConfirm", { name: user.display_name }),
              )
            }
          >
            <KeyRound /> {t("members.reset")}
          </Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => void run(() => api.updateUser(user.id, { is_admin: !user.is_admin }))}>
            <ShieldCheck /> {user.is_admin ? t("members.removeAdmin") : t("members.makeAdmin")}
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() =>
              void run(
                () => api.updateUser(user.id, { disabled: !user.disabled }),
                user.disabled ? undefined : t("members.disableConfirm", { name: user.display_name }),
              )
            }
          >
            {user.disabled ? <UserCheck /> : <UserX />} {user.disabled ? t("members.enable") : t("members.disable")}
          </Button>
        </div>
      )}
    </li>
  );
}

function MembersTile() {
  const { t } = useI18n();
  const users = useData(() => api.users(), "users");
  const me = useData(() => api.me(), "me");
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [asAdmin, setAsAdmin] = useState(false);
  const [busy, setBusy] = useState(false);
  const [oneTime, setOneTime] = useState<OneTimePassword | null>(null);
  const valid = username.trim().length >= 3;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!valid) return;
    setBusy(true);
    try {
      setOneTime(await api.addUser({ username: username.trim(), display_name: displayName.trim() || undefined, is_admin: asAdmin }));
      setUsername("");
      setDisplayName("");
      setAsAdmin(false);
      await users.reload();
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Tile index={4} title={t("settings.members")}>
      {!users.data || !me.data ? (
        <Skeleton className="h-16 rounded-xl" />
      ) : (
        <ul className="space-y-1.5" data-testid="members">
          {users.data.map((user) => (
            <MemberRow key={user.id} user={user} me={me.data!} onChanged={() => void users.reload()} onOneTime={setOneTime} />
          ))}
        </ul>
      )}
      {oneTime && <OneTimePasswordPanel name={oneTime.user.display_name} password={oneTime.one_time_password} onDone={() => setOneTime(null)} />}
      {me.data && !me.data.is_admin ? (
        <p className="border-t pt-3 text-sm text-muted-foreground">{t("members.adminOnly")}</p>
      ) : (
        <form onSubmit={submit} className="space-y-3 border-t pt-3">
          <h3 className="text-sm font-medium">{t("settings.addMember")}</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="member-username">{t("auth.username")}</Label>
              <Input id="member-username" autoComplete="off" value={username} onChange={(e) => setUsername(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="member-name">{t("auth.displayName")}</Label>
              <Input id="member-name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={asAdmin} onChange={(e) => setAsAdmin(e.target.checked)} className="size-4 accent-primary" />
            {t("members.asAdmin")}
          </label>
          <Button type="submit" disabled={busy || !valid}>
            <Plus /> {t("common.add")}
          </Button>
        </form>
      )}
    </Tile>
  );
}

type CategoryDraft = { key: string; name_de: string; name_en: string; kind: Category["kind"]; color: string; is_food: boolean };

// The key is an internal id; anything typed is turned into a valid one, and
// without input it comes from the German name. The hint shows the result.
function KeyField({ idPrefix, draft, onChange }: { idPrefix: string; draft: CategoryDraft; onChange: (changes: Partial<CategoryDraft>) => void }) {
  const { t } = useI18n();
  const key = effectiveKey(draft.key, draft.name_de);
  const invalid = (draft.key.trim() !== "" || draft.name_de.trim() !== "") && !KEY_RE.test(key);
  return (
    <div className="space-y-1.5">
      <Label htmlFor={`${idPrefix}-key`}>{t("settings.key")}</Label>
      <Input
        id={`${idPrefix}-key`}
        value={draft.key}
        placeholder={toCategoryKey(draft.name_de)}
        maxLength={64}
        autoCapitalize="none"
        aria-invalid={invalid}
        aria-describedby={`${idPrefix}-key-hint`}
        onChange={(e) => onChange({ key: e.target.value })}
      />
      <p id={`${idPrefix}-key-hint`} className="text-xs text-muted-foreground" data-testid="category-key-hint">
        {key ? t("settings.keySaved", { key }) : t("settings.keyHint")}
        {invalid && ` ${t("settings.keyTooShort")}`}
      </p>
    </div>
  );
}

function CategoryFields({
  idPrefix,
  draft,
  onChange,
  withKey,
}: {
  idPrefix: string;
  draft: CategoryDraft;
  onChange: (changes: Partial<CategoryDraft>) => void;
  withKey: boolean;
}) {
  const { t } = useI18n();
  return (
    <>
      {withKey && <KeyField idPrefix={idPrefix} draft={draft} onChange={onChange} />}
      <div className="space-y-1.5">
        <Label htmlFor={`${idPrefix}-de`}>{t("settings.nameDe")}</Label>
        <Input id={`${idPrefix}-de`} value={draft.name_de} onChange={(e) => onChange({ name_de: e.target.value })} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${idPrefix}-en`}>{t("settings.nameEn")}</Label>
        <Input id={`${idPrefix}-en`} value={draft.name_en} onChange={(e) => onChange({ name_en: e.target.value })} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${idPrefix}-kind`}>{t("settings.kind")}</Label>
        <select id={`${idPrefix}-kind`} value={draft.kind} onChange={(e) => onChange({ kind: e.target.value as Category["kind"] })} className={SELECT_CLASS}>
          <option value="variable">{t("dash.variable")}</option>
          <option value="fixed">{t("dash.fixed")}</option>
          <option value="income">{t("settings.kindIncome")}</option>
        </select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${idPrefix}-color`}>{t("settings.color")}</Label>
        <input id={`${idPrefix}-color`} type="color" value={draft.color} onChange={(e) => onChange({ color: e.target.value })} className={COLOR_CLASS} />
      </div>
      <label className="flex items-center gap-2 self-end pb-2 text-sm">
        <input type="checkbox" checked={draft.is_food} onChange={(e) => onChange({ is_food: e.target.checked })} className="size-4" />
        {t("settings.isFood")}
      </label>
    </>
  );
}


function CategoryRow({ category, onSaved }: { category: Category; onSaved: () => Promise<void> }) {
  const { t, locale } = useI18n();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<CategoryDraft>(category);
  const [busy, setBusy] = useState(false);
  const valid = draft.name_de.trim() !== "" && draft.name_en.trim() !== "";

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!valid) return;
    setBusy(true);
    try {
      const body: CategoryBody = {
        key: category.key,
        name_de: draft.name_de.trim(),
        name_en: draft.name_en.trim(),
        kind: draft.kind,
        color: draft.color,
        icon: category.icon,
        is_food: draft.is_food,
      };
      await api.updateCategory(category.id, body);
      toast.success(t("receipt.saved"));
      await onSaved();
      setEditing(false);
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const kindLabel = category.kind === "fixed" ? t("dash.fixed") : category.kind === "income" ? t("settings.kindIncome") : t("dash.variable");

  if (!editing) {
    return (
      <li data-testid="category-row" className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl bg-muted/40 px-3 py-2 text-sm">
        <span className="size-4 shrink-0 rounded-full border" style={{ background: category.color }} aria-hidden />
        <span className="min-w-0 flex-1 basis-40">
          <span className="font-medium">{locale === "de" ? category.name_de : category.name_en}</span>
          <span className="ml-2 text-xs text-muted-foreground">{locale === "de" ? category.name_en : category.name_de}</span>
        </span>
        {category.is_food && <Badge variant="outline">{t("settings.isFood")}</Badge>}
        <Badge variant={category.kind === "fixed" ? "default" : category.kind === "income" ? "outline" : "secondary"}>{kindLabel}</Badge>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            setDraft(category);
            setEditing(true);
          }}
        >
          {t("common.edit")}
        </Button>
      </li>
    );
  }

  return (
    <li data-testid="category-row" className="rounded-xl bg-muted/40 p-3">
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <CategoryFields idPrefix={`cat-${category.id}`} draft={draft} withKey={false} onChange={(changes) => setDraft({ ...draft, ...changes })} />
        <div className="flex gap-2 sm:col-span-2 lg:col-span-4">
          <Button type="submit" disabled={busy || !valid}>
            {t("common.save")}
          </Button>
          <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
            {t("common.cancel")}
          </Button>
        </div>
      </form>
    </li>
  );
}

function CategoriesTile() {
  const { t } = useI18n();
  const categories = useData(() => api.categories(), "categories");
  const empty: CategoryDraft = { key: "", name_de: "", name_en: "", kind: "variable", color: "#6366f1", is_food: false };
  const [draft, setDraft] = useState<CategoryDraft>(empty);
  const [busy, setBusy] = useState(false);
  const key = effectiveKey(draft.key, draft.name_de);
  const valid = KEY_RE.test(key) && draft.name_de.trim() !== "" && draft.name_en.trim() !== "";

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!valid) return;
    setBusy(true);
    try {
      await api.createCategory({
        key,
        name_de: draft.name_de.trim(),
        name_en: draft.name_en.trim(),
        kind: draft.kind,
        color: draft.color,
        icon: "",
        is_food: draft.is_food,
      });
      toast.success(t("settings.addCategory"));
      setDraft(empty);
      await categories.reload();
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Tile index={5} title={t("settings.categories")} className="md:col-span-2">
      {!categories.data ? (
        <Skeleton className="h-32 rounded-xl" />
      ) : (
        <ul className="space-y-1.5">
          {categories.data.map((category) => (
            <CategoryRow
              key={`${category.id}:${category.name_de}:${category.name_en}:${category.kind}:${category.color}:${category.is_food}`}
              category={category}
              onSaved={categories.reload}
            />
          ))}
        </ul>
      )}
      <form onSubmit={submit} className="space-y-3 border-t pt-3">
        <h3 className="text-sm font-medium">{t("settings.addCategory")}</h3>
        <div className={cn("grid gap-3 sm:grid-cols-2 lg:grid-cols-6")}>
          <CategoryFields idPrefix="cat-new" draft={draft} withKey onChange={(changes) => setDraft({ ...draft, ...changes })} />
        </div>
        <Button type="submit" disabled={busy || !valid}>
          <Plus /> {t("common.add")}
        </Button>
      </form>
    </Tile>
  );
}

function TagRow({ tag, onChanged }: { tag: Tag; onChanged: () => void }) {
  const { t } = useI18n();
  const uid = useId();
  const [name, setName] = useState(tag.name);
  const [color, setColor] = useState(tag.color);
  const [busy, setBusy] = useState(false);
  const dirty = name.trim() !== tag.name || color !== tag.color;

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
    <li className="flex flex-wrap items-end gap-2 rounded-xl bg-muted/40 px-3 py-2" data-testid="tag-row">
      <div className="min-w-40 flex-1 space-y-1">
        <Label htmlFor={`${uid}-name`} className="text-xs">
          {t("tags.name")}
        </Label>
        <Input id={`${uid}-name`} value={name} maxLength={64} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="space-y-1">
        <Label htmlFor={`${uid}-color`} className="text-xs">
          {t("tags.color")}
        </Label>
        <input id={`${uid}-color`} type="color" value={color} onChange={(e) => setColor(e.target.value)} className={COLOR_CLASS} />
      </div>
      <Button
        size="sm"
        variant="outline"
        disabled={busy || !dirty || !name.trim()}
        aria-label={t("tags.rename", { name: tag.name })}
        onClick={() => void run(() => api.updateTag(tag.id, { name: name.trim(), color }))}
      >
        {t("common.save")}
      </Button>
      <Button
        size="sm"
        variant="ghost"
        className="text-destructive"
        disabled={busy}
        aria-label={t("tags.delete", { name: tag.name })}
        onClick={() => window.confirm(t("tags.deleteConfirm", { name: tag.name })) && void run(() => api.deleteTag(tag.id))}
      >
        <Trash2 />
      </Button>
    </li>
  );
}

function TagsTile() {
  const { t } = useI18n();
  const tags = useData(() => api.tags(), "tags");
  return (
    <Tile index={6} title={t("tags.title")} className="md:col-span-2" testId="tags-tile">
      {!tags.data ? (
        <Skeleton className="h-16 rounded-xl" />
      ) : tags.data.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("tags.empty")}</p>
      ) : (
        <ul className="space-y-1.5">
          {tags.data.map((tag) => (
            <TagRow key={`${tag.id}:${tag.name}:${tag.color}`} tag={tag} onChanged={() => void tags.reload()} />
          ))}
        </ul>
      )}
    </Tile>
  );
}

type AccountDraft = BankAccountInput;

function AccountFields({
  idPrefix,
  draft,
  card = "",
  onChange,
}: {
  idPrefix: string;
  draft: AccountDraft;
  // a credit card: its number comes from the statement, there is no IBAN
  card?: string;
  onChange: (d: Partial<AccountDraft>) => void;
}) {
  const { t } = useI18n();
  return (
    <>
      <div className="min-w-0 space-y-1">
        <Label htmlFor={`${idPrefix}-name`} className="text-xs">
          {t("accounts.name")}
        </Label>
        <Input id={`${idPrefix}-name`} value={draft.name} maxLength={64} onChange={(e) => onChange({ name: e.target.value })} />
      </div>
      <div className="min-w-0 space-y-1">
        <Label htmlFor={`${idPrefix}-bank`} className="text-xs">
          {t("accounts.bank")}
        </Label>
        <Input id={`${idPrefix}-bank`} value={draft.bank} maxLength={64} onChange={(e) => onChange({ bank: e.target.value })} />
      </div>
      {!card && (
        <div className="min-w-0 space-y-1">
          <Label htmlFor={`${idPrefix}-kind`} className="text-xs">
            {t("accounts.kind")}
          </Label>
          <select
            id={`${idPrefix}-kind`}
            value={draft.kind}
            onChange={(e) => onChange({ kind: e.target.value as AccountDraft["kind"] })}
            className={SELECT_CLASS}
          >
            <option value="giro">{t("accounts.kindGiro")}</option>
            <option value="savings">{t("accounts.kindSavings")}</option>
          </select>
        </div>
      )}
      {card ? (
        <div className="min-w-0 space-y-1">
          <div className="text-xs font-medium">{t("accounts.card")}</div>
          <div className="flex h-9 items-center font-mono text-sm" data-testid="account-card">
            …{card.slice(-4)}
          </div>
        </div>
      ) : (
        <div className="min-w-0 space-y-1">
          <Label htmlFor={`${idPrefix}-iban`} className="text-xs">
            {t("accounts.iban")}
          </Label>
          <Input
            id={`${idPrefix}-iban`}
            value={draft.iban}
            maxLength={42}
            autoCapitalize="characters"
            spellCheck={false}
            className="font-mono"
            onChange={(e) => onChange({ iban: e.target.value })}
          />
        </div>
      )}
      <div className="space-y-1">
        <Label htmlFor={`${idPrefix}-color`} className="text-xs">
          {t("accounts.color")}
        </Label>
        <input id={`${idPrefix}-color`} type="color" value={draft.color} onChange={(e) => onChange({ color: e.target.value })} className={COLOR_CLASS} />
      </div>
    </>
  );
}

function accountError(error: unknown, t: (key: MessageKey) => string): string {
  const message = (error as Error).message;
  return message === "invalid_iban" ? t("accounts.invalidIban") : message;
}

function AccountRow({ account, onChanged }: { account: BankAccount; onChanged: () => void }) {
  const { t } = useI18n();
  const uid = useId();
  const [draft, setDraft] = useState<AccountDraft>({
    name: account.name,
    bank: account.bank,
    iban: account.iban,
    kind: account.kind === "savings" ? "savings" : "giro",
    color: account.color,
  });
  const [busy, setBusy] = useState(false);
  const dirty =
    draft.name.trim() !== account.name ||
    draft.bank.trim() !== account.bank ||
    draft.iban.replace(/\s/g, "").toUpperCase() !== account.iban ||
    (account.kind !== "card" && draft.kind !== account.kind) ||
    draft.color !== account.color;

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    try {
      await action();
      onChanged();
    } catch (error) {
      toast.error(accountError(error, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="space-y-2 rounded-xl bg-muted/40 px-3 py-2" data-testid="account-row">
      <div className="grid grid-cols-1 items-end gap-2 sm:grid-cols-[1fr_1fr_auto_1.4fr_auto]">
        <AccountFields idPrefix={uid} draft={draft} card={account.card_number} onChange={(changes) => setDraft({ ...draft, ...changes })} />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted-foreground">{t("accounts.bookings", { n: account.bookings })}</span>
        <Button
          size="sm"
          variant="outline"
          className="ml-auto"
          disabled={busy || !dirty || !draft.name.trim()}
          aria-label={t("accounts.save", { name: account.name })}
          onClick={() => void run(() => api.updateAccount(account.id, draft))}
        >
          {t("common.save")}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="text-destructive"
          disabled={busy}
          aria-label={t("accounts.delete", { name: account.name })}
          onClick={() => window.confirm(t("accounts.deleteConfirm", { name: account.name })) && void run(() => api.deleteAccount(account.id))}
        >
          <Trash2 />
        </Button>
      </div>
    </li>
  );
}

function AccountsTile() {
  const { t } = useI18n();
  const accounts = useData(() => api.accounts(), "accounts");
  const empty: AccountDraft = { name: "", bank: "", iban: "", kind: "giro", color: "#64748b" };
  const [draft, setDraft] = useState<AccountDraft>(empty);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft.name.trim()) return;
    setBusy(true);
    try {
      await api.createAccount(draft);
      setDraft(empty);
      await accounts.reload();
    } catch (error) {
      toast.error(accountError(error, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Tile index={7} title={t("accounts.title")} className="md:col-span-2" testId="accounts-tile">
      <p className="text-sm text-muted-foreground">{t("accounts.hint")}</p>
      {!accounts.data ? (
        <Skeleton className="h-16 rounded-xl" />
      ) : accounts.data.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("accounts.empty")}</p>
      ) : (
        <ul className="space-y-1.5">
          {accounts.data.map((account) => (
            <AccountRow key={`${account.id}:${account.name}:${account.bank}:${account.iban}:${account.kind}:${account.color}:${account.bookings}`} account={account} onChanged={() => void accounts.reload()} />
          ))}
        </ul>
      )}
      <form onSubmit={submit} className="space-y-3 border-t pt-3">
        <h3 className="text-sm font-medium">{t("accounts.add")}</h3>
        <div className="grid grid-cols-1 items-end gap-2 sm:grid-cols-[1fr_1fr_auto_1.4fr_auto]">
          <AccountFields idPrefix="account-new" draft={draft} onChange={(changes) => setDraft({ ...draft, ...changes })} />
        </div>
        <Button type="submit" disabled={busy || !draft.name.trim()}>
          <Plus /> {t("accounts.add")}
        </Button>
      </form>
    </Tile>
  );
}

function merchantError(error: unknown, t: (key: MessageKey) => string): string {
  const message = (error as Error).message;
  return message === "merchant_exists" ? t("merchants.exists") : message === "invalid_keyword" ? t("merchants.invalid") : message;
}

function MerchantRow({ merchant, categories, onChanged }: { merchant: Merchant; categories: Category[]; onChanged: () => void }) {
  const { t, locale } = useI18n();
  const uid = useId();
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<unknown>, message: MessageKey) {
    setBusy(true);
    try {
      await action();
      toast.success(t(message));
      onChanged();
    } catch (error) {
      toast.error(merchantError(error, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="flex flex-wrap items-center gap-2 rounded-xl bg-muted/50 px-3 py-2" data-testid="merchant-row">
      <span className="min-w-24 flex-1 truncate font-medium">{merchant.keyword}</span>
      <Label htmlFor={`${uid}-category`} className="sr-only">
        {t("merchants.categoryFor", { name: merchant.keyword })}
      </Label>
      <select
        id={`${uid}-category`}
        value={merchant.category_id}
        disabled={busy}
        onChange={(e) =>
          void run(() => api.updateMerchant(merchant.id, { keyword: merchant.keyword, category_id: Number(e.target.value) }), "merchants.saved")
        }
        className={cn(SELECT_CLASS, "w-auto min-w-0 flex-1")}
      >
        {categories.map((c) => (
          <option key={c.id} value={c.id}>
            {locale === "de" ? c.name_de : c.name_en}
          </option>
        ))}
      </select>
      <Button
        size="icon-sm"
        variant="ghost"
        className="text-destructive"
        disabled={busy}
        aria-label={t("merchants.remove", { name: merchant.keyword })}
        onClick={() => void run(() => api.deleteMerchant(merchant.id), "merchants.removed")}
      >
        <Trash2 />
      </Button>
    </li>
  );
}

function MerchantsTile() {
  const { t, locale } = useI18n();
  const merchants = useData(() => api.merchants(), "merchants");
  const categoryList = useData(() => api.categories(), "categories");
  const categories = spendingCategories(categoryList.data ?? []).sort((a, b) =>
    (locale === "de" ? a.name_de : a.name_en).localeCompare(locale === "de" ? b.name_de : b.name_en, locale),
  );
  const [keyword, setKeyword] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [busy, setBusy] = useState(false);
  const chosen = categoryId || String(categories.find((c) => c.key === "groceries")?.id ?? "");

  async function add(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await api.createMerchant({ keyword, category_id: Number(chosen) });
      setKeyword("");
      toast.success(t("merchants.added"));
      await merchants.reload();
    } catch (error) {
      toast.error(merchantError(error, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Tile index={9} title={t("merchants.title")} className="md:col-span-2" testId="merchants-tile">
      <p className="mb-3 text-sm text-muted-foreground">{t("merchants.hint")}</p>
      {!merchants.data || !categoryList.data ? (
        <Skeleton className="h-16 rounded-xl" />
      ) : (
        <>
          {merchants.data.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("merchants.empty")}</p>
          ) : (
            <ul className="space-y-1.5">
              {merchants.data.map((m) => (
                <MerchantRow key={`${m.id}:${m.category_id}`} merchant={m} categories={categories} onChanged={() => void merchants.reload()} />
              ))}
            </ul>
          )}
          <form onSubmit={add} className="mt-3 flex flex-wrap items-end gap-2">
            <div className="min-w-32 flex-1 space-y-1">
              <Label htmlFor="merchant-keyword" className="text-xs">
                {t("merchants.keyword")}
              </Label>
              <Input id="merchant-keyword" value={keyword} maxLength={64} onChange={(e) => setKeyword(e.target.value)} required />
            </div>
            <div className="min-w-32 flex-1 space-y-1">
              <Label htmlFor="merchant-category" className="text-xs">
                {t("merchants.category")}
              </Label>
              <select id="merchant-category" value={chosen} onChange={(e) => setCategoryId(e.target.value)} className={SELECT_CLASS}>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {locale === "de" ? c.name_de : c.name_en}
                  </option>
                ))}
              </select>
            </div>
            <Button type="submit" disabled={busy || !keyword.trim() || !chosen}>
              <Plus /> {t("merchants.add")}
            </Button>
          </form>
        </>
      )}
    </Tile>
  );
}

function NewTokenPanel({ token, onDone }: { token: NewApiToken; onDone: () => void }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  const example = `curl -H "Authorization: Bearer ${token.token}" -F files=@bon.jpg ${origin}/api/v1/receipts`;
  return (
    <div role="status" className="space-y-2 rounded-xl border-2 border-primary p-3" data-testid="new-api-token">
      <p className="text-sm font-medium">{t("apiTokens.newTitle", { name: token.name })}</p>
      <p className="break-all font-mono text-sm select-all" data-testid="api-token-value">
        {token.token}
      </p>
      <p className="text-xs text-muted-foreground">{t("apiTokens.newHint")}</p>
      <pre className="rounded-lg bg-muted/60 p-2 font-mono text-xs break-all whitespace-pre-wrap">{example}</pre>
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() =>
            void navigator.clipboard
              ?.writeText(token.token)
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

function ApiTokenRow({ token, onChanged }: { token: ApiToken; onChanged: () => void }) {
  const { t, locale } = useI18n();
  const [busy, setBusy] = useState(false);

  async function revoke() {
    if (!window.confirm(t("apiTokens.revokeConfirm", { name: token.name }))) return;
    setBusy(true);
    try {
      await api.revokeApiToken(token.id);
      toast.success(t("apiTokens.revoked"));
      onChanged();
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="flex flex-wrap items-center gap-2 rounded-xl bg-muted/50 px-3 py-2" data-testid="api-token-row">
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">
          {token.name} <span className="font-mono text-xs text-muted-foreground">…{token.hint}</span>
        </p>
        <p className="text-xs text-muted-foreground">
          {token.last_used_at ? t("apiTokens.lastUsed", { when: dateTime(token.last_used_at, locale) }) : t("apiTokens.neverUsed")}
        </p>
      </div>
      <Button
        size="icon-sm"
        variant="ghost"
        className="text-destructive"
        disabled={busy}
        aria-label={t("apiTokens.revoke", { name: token.name })}
        onClick={() => void revoke()}
      >
        <Trash2 />
      </Button>
    </li>
  );
}

function ApiTokensTile() {
  const { t } = useI18n();
  const tokens = useData(() => api.apiTokens(), "api-tokens");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<NewApiToken | null>(null);

  async function add(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      setCreated(await api.createApiToken(name.trim()));
      setName("");
      toast.success(t("apiTokens.created"));
      await tokens.reload();
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Tile index={11} title={t("apiTokens.title")} className="md:col-span-2" testId="api-tokens-tile">
      <p className="mb-3 text-sm text-muted-foreground">{t("apiTokens.hint")}</p>
      {created && <NewTokenPanel token={created} onDone={() => setCreated(null)} />}
      {!tokens.data ? (
        <Skeleton className="h-16 rounded-xl" />
      ) : tokens.data.length === 0 ? (
        <p className="mt-3 text-sm text-muted-foreground">{t("apiTokens.empty")}</p>
      ) : (
        <ul className="mt-3 space-y-1.5">
          {tokens.data.map((token) => (
            <ApiTokenRow key={token.id} token={token} onChanged={() => void tokens.reload()} />
          ))}
        </ul>
      )}
      <form onSubmit={add} className="mt-3 flex flex-wrap items-end gap-2">
        <div className="min-w-32 flex-1 space-y-1">
          <Label htmlFor="api-token-name" className="text-xs">
            {t("apiTokens.name")}
          </Label>
          <Input id="api-token-name" value={name} maxLength={64} onChange={(e) => setName(e.target.value)} required />
        </div>
        <Button type="submit" disabled={busy || !name.trim()}>
          <Plus /> {t("apiTokens.add")}
        </Button>
      </form>
    </Tile>
  );
}

function ResetTile() {
  const { t, locale } = useI18n();
  const me = useData(() => api.me(), "me");
  const current = useData(() => api.resetDate(), "reset-date");
  const [day, setDay] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const since = current.data?.since ?? null;
  const value = day ?? since ?? localToday();

  async function save(next: string | null) {
    setBusy(true);
    try {
      current.setData(await api.saveResetDate(next));
      setDay(null);
      toast.success(next ? t("reset.saved") : t("reset.lifted"));
    } catch (error) {
      const message = (error as Error).message;
      toast.error(message === "reset_in_future" ? t("reset.future") : message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Tile index={10} title={t("reset.title")} testId="reset-tile">
      {!current.data || !me.data ? (
        <Skeleton className="h-28 rounded-xl" />
      ) : (
        <div className="space-y-3">
          <p className="text-sm" data-testid="reset-state">
            {since ? t("reset.active", { date: shortDate(since, locale) }) : t("reset.none")}
          </p>
          <p className="text-xs text-muted-foreground">{t("reset.hint")}</p>
          {me.data.is_admin ? (
            <>
              <div className="space-y-1.5">
                <Label htmlFor="reset-date">{t("reset.date")}</Label>
                <Input id="reset-date" type="date" max={localToday()} value={value} onChange={(e) => setDay(e.target.value)} />
              </div>
              <div className="flex flex-wrap gap-2">
                <Button disabled={busy || !value} onClick={() => void save(value)}>
                  {t("reset.apply")}
                </Button>
                {since && (
                  <Button variant="outline" disabled={busy} onClick={() => void save(null)}>
                    {t("reset.lift")}
                  </Button>
                )}
              </div>
            </>
          ) : (
            <p className="text-xs text-muted-foreground">{t("reset.adminOnly")}</p>
          )}
        </div>
      )}
    </Tile>
  );
}

function OneOffTile() {
  const { t } = useI18n();
  const settings = useData(() => api.bankSettings(), "bank-settings");
  const [euros, setEuros] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const value = euros ?? (settings.data ? String(settings.data.one_off_threshold_cents / 100) : "");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const saved = await api.saveBankSettings({ one_off_threshold_cents: Math.round(Number(value) * 100) });
      settings.setData(saved);
      setEuros(null);
      toast.success(t("receipt.saved"));
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Tile index={8} title={t("oneOff.title")} testId="one-off-tile">
      {!settings.data ? (
        <Skeleton className="h-28 rounded-xl" />
      ) : (
        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="one-off-threshold">{t("oneOff.threshold")}</Label>
            <Input
              id="one-off-threshold"
              type="number"
              inputMode="decimal"
              min={0}
              max={1000000}
              step={1}
              value={value}
              onChange={(e) => setEuros(e.target.value)}
              aria-describedby="one-off-threshold-hint"
              required
            />
            <p id="one-off-threshold-hint" className="text-xs text-muted-foreground">
              {t("oneOff.hint")}
            </p>
          </div>
          <Button type="submit" disabled={busy || value === ""}>
            {t("common.save")}
          </Button>
        </form>
      )}
    </Tile>
  );
}

export function Settings() {
  const { t } = useI18n();
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">{t("settings.title")}</h1>
      <div className="grid gap-4 md:grid-cols-2">
        <LanguageTile />
        <ThemeTile />
        <ProfileTile />
        <HouseholdTile />
        <PasswordTile />
        <MembersTile />
        <CategoriesTile />
        <TagsTile />
        <AccountsTile />
        <OneOffTile />
        <ResetTile />
        <MerchantsTile />
        <ApiTokensTile />
      </div>
    </div>
  );
}
