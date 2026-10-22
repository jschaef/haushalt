"use client";

import { AnimatePresence, motion } from "motion/react";
import { useTheme } from "next-themes";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Camera, Eye, Gauge, Landmark, LayoutGrid, Languages, Receipt, Repeat, Search, Settings, SunMoon, Store as StoreIcon } from "lucide-react";
import { api, type Store } from "@/lib/api";
import { useI18n } from "@/lib/i18n/provider";
import { useScan } from "@/components/scan";
import { cn } from "@/lib/utils";

type Command = { id: string; group: string; label: string; icon: ReactNode; run: () => void; hint?: string };

// Cmd/Ctrl+K: jump anywhere, toggle theme or language, find a store.
export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { t, locale, setLocale } = useI18n();
  const { resolvedTheme, setTheme } = useTheme();
  const router = useRouter();
  const scan = useScan();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [stores, setStores] = useState<Store[]>([]);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        onOpenChange(!open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  useEffect(() => {
    if (!open) return;
    api.stores().then(setStores, () => setStores([]));
    const timer = setTimeout(() => input.current?.focus(), 30);
    return () => clearTimeout(timer);
  }, [open]);

  const commands = useMemo<Command[]>(() => {
    const go = (href: string) => () => router.push(href);
    const nav = t("palette.navigate");
    const actions = t("palette.actions");
    return [
      { id: "dashboard", group: nav, label: t("nav.dashboard"), icon: <LayoutGrid />, run: go("/dashboard") },
      { id: "receipts", group: nav, label: t("nav.receipts"), icon: <Receipt />, run: go("/receipts") },
      { id: "drafts", group: nav, label: t("receipts.drafts"), icon: <Receipt />, run: go("/receipts?status=draft") },
      { id: "fixed", group: nav, label: t("nav.fixed"), icon: <Repeat />, run: go("/fixed") },
      { id: "utilities", group: nav, label: t("nav.utilities"), icon: <Gauge />, run: go("/utilities") },
      { id: "bank", group: nav, label: t("nav.bank"), icon: <Landmark />, run: go("/bank") },
      { id: "settings", group: nav, label: t("nav.settings"), icon: <Settings />, run: go("/settings") },
      { id: "scan", group: actions, label: t("nav.scan"), icon: <Camera />, run: scan.openCamera },
      { id: "theme", group: actions, label: t("palette.toggleTheme"), icon: <SunMoon />, run: () => setTheme(resolvedTheme === "light" ? "dark" : "light") },
      { id: "contrast", group: actions, label: t("a11y.contrast"), icon: <Eye />, run: () => setTheme(resolvedTheme === "contrast" ? "dark" : "contrast") },
      { id: "language", group: actions, label: t("palette.toggleLanguage"), icon: <Languages />, run: () => setLocale(locale === "de" ? "en" : "de") },
      ...stores.map((store) => ({
        id: `store-${store.id}`,
        group: t("palette.stores"),
        label: store.name,
        hint: `${store.receipts}×`,
        icon: <StoreIcon />,
        run: go(`/receipts?store=${encodeURIComponent(store.name)}`),
      })),
    ];
  }, [t, router, scan.openCamera, setTheme, resolvedTheme, setLocale, locale, stores]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return needle ? commands.filter((c) => c.label.toLowerCase().includes(needle)) : commands;
  }, [commands, query]);

  const close = () => {
    onOpenChange(false);
    setQuery("");
    setActive(0);
  };
  const run = (command: Command | undefined) => {
    if (!command) return;
    close();
    command.run();
  };

  let lastGroup = "";
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 pt-[12vh] backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={close}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label={t("palette.placeholder")}
            className="glass w-full max-w-lg overflow-hidden rounded-2xl"
            initial={{ y: -12, scale: 0.97 }}
            animate={{ y: 0, scale: 1 }}
            exit={{ y: -8, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 420, damping: 32 }}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center gap-2 border-b px-4">
              <Search className="size-4 text-muted-foreground" />
              <input
                ref={input}
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                  setActive(0);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Escape") close();
                  if (event.key === "ArrowDown") {
                    event.preventDefault();
                    setActive((i) => Math.min(i + 1, filtered.length - 1));
                  }
                  if (event.key === "ArrowUp") {
                    event.preventDefault();
                    setActive((i) => Math.max(i - 1, 0));
                  }
                  if (event.key === "Enter") run(filtered[active]);
                }}
                placeholder={t("palette.placeholder")}
                className="h-12 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                role="combobox"
                aria-expanded="true"
                aria-controls="palette-list"
              />
              <kbd className="rounded border px-1.5 text-[10px] text-muted-foreground">ESC</kbd>
            </div>
            <ul id="palette-list" role="listbox" className="max-h-[50vh] overflow-y-auto p-2">
              {filtered.length === 0 && <li className="px-3 py-6 text-center text-sm text-muted-foreground">{t("palette.empty")}</li>}
              {filtered.map((command, index) => {
                const header = command.group !== lastGroup ? command.group : null;
                lastGroup = command.group;
                return (
                  <li key={command.id} role="presentation">
                    {header && <div className="px-3 pb-1 pt-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{header}</div>}
                    <button
                      type="button"
                      role="option"
                      aria-selected={index === active}
                      onMouseEnter={() => setActive(index)}
                      onClick={() => run(command)}
                      className={cn(
                        "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm [&_svg]:size-4 [&_svg]:text-muted-foreground",
                        index === active && "bg-accent text-accent-foreground",
                      )}
                    >
                      {command.icon}
                      <span className="flex-1">{command.label}</span>
                      {command.hint && <span className="text-xs text-muted-foreground">{command.hint}</span>}
                    </button>
                  </li>
                );
              })}
            </ul>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
