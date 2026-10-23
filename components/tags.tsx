"use client";

import { useId, useState } from "react";
import { Check, Plus } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, type Tag } from "@/lib/api";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";

// Tags say for whom or what for (a family member, a holiday), next to the one
// category of an entry. The page loads the list once and passes it down.

function Dot({ color }: { color: string }) {
  return <span className="size-2.5 shrink-0 rounded-full ring-1 ring-foreground/40" style={{ background: color }} aria-hidden />;
}

export function TagChips({ ids, tags }: { ids: number[]; tags: Tag[] }) {
  const shown = tags.filter((tag) => ids.includes(tag.id));
  if (!shown.length) return null;
  return (
    <ul className="flex flex-wrap gap-1" data-testid="tag-chips">
      {shown.map((tag) => (
        <li key={tag.id} className="inline-flex max-w-full items-center gap-1 rounded-full border px-2 py-0.5 text-xs">
          <Dot color={tag.color} />
          <span className="truncate">{tag.name}</span>
        </li>
      ))}
    </ul>
  );
}

export function TagPicker({
  tags,
  selected,
  onChange,
  onCreated,
}: {
  tags: Tag[];
  selected: number[];
  onChange: (ids: number[]) => void;
  onCreated: (tag: Tag) => void;
}) {
  const { t } = useI18n();
  const uid = useId();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  function toggle(id: number) {
    onChange(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);
  }

  async function create() {
    const clean = name.trim();
    if (!clean) return;
    // an existing tag of that name is simply selected
    const existing = tags.find((tag) => tag.name.toLowerCase() === clean.toLowerCase());
    if (existing) {
      if (!selected.includes(existing.id)) onChange([...selected, existing.id]);
      setName("");
      return;
    }
    setBusy(true);
    try {
      const tag = await api.createTag({ name: clean, color: "#64748b" });
      onCreated(tag);
      onChange([...selected, tag.id]);
      setName("");
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    // min-w-0: a fieldset is at least as wide as its content by default and
    // would widen the whole form grid on narrow screens (WCAG 1.4.10 reflow)
    <fieldset className="min-w-0 space-y-2" data-testid="tag-picker">
      <legend className="text-sm font-medium">{t("tags.title")}</legend>
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {tags.map((tag) => {
            const on = selected.includes(tag.id);
            return (
              <Button
                key={tag.id}
                type="button"
                size="sm"
                variant={on ? "default" : "outline"}
                aria-pressed={on}
                onClick={() => toggle(tag.id)}
                className="max-w-full"
              >
                {on ? <Check /> : <Dot color={tag.color} />} <span className="truncate">{tag.name}</span>
              </Button>
            );
          })}
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <label htmlFor={`${uid}-new`} className="sr-only">
          {t("tags.new")}
        </label>
        <Input
          id={`${uid}-new`}
          value={name}
          maxLength={64}
          placeholder={t("tags.new")}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            // Enter adds the tag instead of submitting the surrounding form
            if (e.key === "Enter") {
              e.preventDefault();
              void create();
            }
          }}
          className="min-w-0 flex-1 basis-40 sm:max-w-56"
        />
        <Button type="button" size="sm" variant="outline" disabled={busy || !name.trim()} onClick={() => void create()}>
          <Plus /> {t("tags.add")}
        </Button>
      </div>
    </fieldset>
  );
}

// "all" or one item; narrows lists by tag (or anything with id, name and
// color, e.g. bank accounts)
export function TagFilter({
  tags,
  value,
  onChange,
  label,
  allLabel,
  testId = "tag-filter",
}: {
  tags: Pick<Tag, "id" | "name" | "color">[];
  value: number | null;
  onChange: (id: number | null) => void;
  label?: string;
  allLabel?: string;
  testId?: string;
}) {
  const { t } = useI18n();
  if (!tags.length) return null;
  return (
    <div role="group" aria-label={label ?? t("tags.filter")} className="flex flex-wrap gap-1.5" data-testid={testId}>
      <Button type="button" size="sm" variant={value === null ? "default" : "outline"} aria-pressed={value === null} onClick={() => onChange(null)}>
        {allLabel ?? t("tags.all")}
      </Button>
      {tags.map((tag) => (
        <Button
          key={tag.id}
          type="button"
          size="sm"
          variant={value === tag.id ? "default" : "outline"}
          aria-pressed={value === tag.id}
          onClick={() => onChange(value === tag.id ? null : tag.id)}
          className={cn("max-w-full gap-1.5")}
        >
          <Dot color={tag.color} /> <span className="truncate">{tag.name}</span>
        </Button>
      ))}
    </div>
  );
}
