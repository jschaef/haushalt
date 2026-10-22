"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useTheme } from "next-themes";
import { Plus } from "lucide-react";
import { toast } from "sonner";
import { Tile } from "@/components/bento";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type Category } from "@/lib/api";
import { useData } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n/provider";
import type { Locale, MessageKey } from "@/lib/i18n/messages";
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
  const options: { value: "dark" | "light" | "system" | "contrast"; label: MessageKey }[] = [
    { value: "dark", label: "settings.themeDark" },
    { value: "light", label: "settings.themeLight" },
    { value: "system", label: "settings.themeSystem" },
    { value: "contrast", label: "settings.themeContrast" },
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

function ProfileTile() {
  const { t } = useI18n();
  const me = useData(() => api.me(), "me");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const loaded = me.data;

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- editable copy of the loaded profile
    if (loaded) setName(loaded.display_name);
  }, [loaded]);

  const passwordInvalid = password !== "" && password.length < 8;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (passwordInvalid || !name.trim()) return;
    setBusy(true);
    try {
      const saved = await api.updateMe({ display_name: name.trim(), ...(password ? { password } : {}) });
      me.setData(saved);
      setPassword("");
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
          <div className="space-y-1.5">
            <Label htmlFor="profile-password">{t("settings.newPassword")}</Label>
            <Input
              id="profile-password"
              type="password"
              autoComplete="new-password"
              minLength={8}
              value={password}
              aria-invalid={passwordInvalid}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <Button type="submit" disabled={busy || passwordInvalid || !name.trim()}>
            {t("common.save")}
          </Button>
        </form>
      )}
    </Tile>
  );
}

function MembersTile() {
  const { t } = useI18n();
  const users = useData(() => api.users(), "users");
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const valid = username.trim() !== "" && password.length >= 8;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!valid) return;
    setBusy(true);
    try {
      await api.addUser({ username: username.trim(), password, display_name: displayName.trim() || undefined });
      toast.success(t("settings.addMember"));
      setUsername("");
      setDisplayName("");
      setPassword("");
      await users.reload();
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Tile index={3} title={t("settings.members")}>
      {!users.data ? (
        <Skeleton className="h-16 rounded-xl" />
      ) : (
        <ul className="space-y-1.5" data-testid="members">
          {users.data.map((user) => (
            <li key={user.id} className="flex items-baseline gap-2 rounded-xl bg-muted/40 px-3 py-2 text-sm">
              <span className="font-medium">{user.display_name}</span>
              <span className="text-xs text-muted-foreground">@{user.username}</span>
            </li>
          ))}
        </ul>
      )}
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
        <div className="space-y-1.5">
          <Label htmlFor="member-password">{t("auth.password")}</Label>
          <Input
            id="member-password"
            type="password"
            autoComplete="new-password"
            minLength={8}
            value={password}
            aria-invalid={password !== "" && password.length < 8}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <Button type="submit" disabled={busy || !valid}>
          <Plus /> {t("common.add")}
        </Button>
      </form>
    </Tile>
  );
}

type CategoryDraft = { key: string; name_de: string; name_en: string; kind: Category["kind"]; color: string };

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
      {withKey && (
        <div className="space-y-1.5">
          <Label htmlFor={`${idPrefix}-key`}>{t("settings.key")}</Label>
          <Input
            id={`${idPrefix}-key`}
            value={draft.key}
            pattern="^[a-z0-9_]+$"
            minLength={2}
            maxLength={48}
            autoCapitalize="none"
            onChange={(e) => onChange({ key: e.target.value })}
          />
        </div>
      )}
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
        </select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${idPrefix}-color`}>{t("settings.color")}</Label>
        <input id={`${idPrefix}-color`} type="color" value={draft.color} onChange={(e) => onChange({ color: e.target.value })} className={COLOR_CLASS} />
      </div>
    </>
  );
}

const KEY_RE = /^[a-z0-9_]{2,48}$/;

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

  const kindLabel = category.kind === "fixed" ? t("dash.fixed") : t("dash.variable");

  if (!editing) {
    return (
      <li data-testid="category-row" className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl bg-muted/40 px-3 py-2 text-sm">
        <span className="size-4 shrink-0 rounded-full border" style={{ background: category.color }} aria-hidden />
        <span className="min-w-0 flex-1 basis-40">
          <span className="font-medium">{locale === "de" ? category.name_de : category.name_en}</span>
          <span className="ml-2 text-xs text-muted-foreground">{locale === "de" ? category.name_en : category.name_de}</span>
        </span>
        <Badge variant={category.kind === "fixed" ? "default" : "secondary"}>{kindLabel}</Badge>
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
  const empty: CategoryDraft = { key: "", name_de: "", name_en: "", kind: "variable", color: "#6366f1" };
  const [draft, setDraft] = useState<CategoryDraft>(empty);
  const [busy, setBusy] = useState(false);
  const valid = KEY_RE.test(draft.key) && draft.name_de.trim() !== "" && draft.name_en.trim() !== "";

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!valid) return;
    setBusy(true);
    try {
      await api.createCategory({
        key: draft.key,
        name_de: draft.name_de.trim(),
        name_en: draft.name_en.trim(),
        kind: draft.kind,
        color: draft.color,
        icon: "",
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
    <Tile index={4} title={t("settings.categories")} className="md:col-span-2">
      {!categories.data ? (
        <Skeleton className="h-32 rounded-xl" />
      ) : (
        <ul className="space-y-1.5">
          {categories.data.map((category) => (
            <CategoryRow key={`${category.id}:${category.name_de}:${category.name_en}:${category.kind}:${category.color}`} category={category} onSaved={categories.reload} />
          ))}
        </ul>
      )}
      <form onSubmit={submit} className="space-y-3 border-t pt-3">
        <h3 className="text-sm font-medium">{t("settings.addCategory")}</h3>
        <div className={cn("grid gap-3 sm:grid-cols-2 lg:grid-cols-5")}>
          <CategoryFields idPrefix="cat-new" draft={draft} withKey onChange={(changes) => setDraft({ ...draft, ...changes })} />
        </div>
        <Button type="submit" disabled={busy || !valid}>
          <Plus /> {t("common.add")}
        </Button>
      </form>
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
        <MembersTile />
        <CategoriesTile />
      </div>
    </div>
  );
}
