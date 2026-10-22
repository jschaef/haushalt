"use client";

import { motion } from "motion/react";
import { useTheme } from "next-themes";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import { Camera, Eye, Gauge, Landmark, LayoutGrid, LogOut, Moon, Receipt, Repeat, Search, Settings, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CommandPalette } from "@/components/command-palette";
import { ScanProvider, useScan } from "@/components/scan";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n/provider";
import type { MessageKey } from "@/lib/i18n/messages";
import { cn } from "@/lib/utils";

const NAV: { href: string; label: MessageKey; icon: typeof LayoutGrid }[] = [
  { href: "/dashboard", label: "nav.dashboard", icon: LayoutGrid },
  { href: "/receipts", label: "nav.receipts", icon: Receipt },
  { href: "/fixed", label: "nav.fixed", icon: Repeat },
  { href: "/utilities", label: "nav.utilities", icon: Gauge },
  { href: "/bank", label: "nav.bank", icon: Landmark },
  { href: "/settings", label: "nav.settings", icon: Settings },
];

// phone tab bar: two links, the camera, two links; fixed costs and the bank
// are reached from the utilities page, the dashboard and the command palette
const TABS = NAV.filter((item) => item.href !== "/fixed" && item.href !== "/bank");

async function logout() {
  await fetch("/api/auth/logout", { method: "POST" });
  // full reload: no state of the old session survives in memory
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  window.location.href = "/login";
}

function LanguageToggle() {
  const { locale, setLocale } = useI18n();
  const next = locale === "de" ? "en" : "de";
  return (
    <Button
      variant="ghost"
      size="sm"
      // the accessible name starts with the visible text (WCAG 2.5.3)
      aria-label={next === "en" ? "EN – Switch to English" : "DE – Auf Deutsch umschalten"}
      onClick={() => {
        setLocale(next);
        void api.updateMe({ locale: next }).catch(() => undefined);
      }}
      className="font-semibold uppercase"
      data-testid="language-toggle"
    >
      {next}
    </Button>
  );
}

function ThemeToggle() {
  const { t } = useI18n();
  const { resolvedTheme, setTheme } = useTheme();
  return (
    <Button variant="ghost" size="icon" aria-label={t("palette.toggleTheme")} onClick={() => setTheme(resolvedTheme === "light" ? "dark" : "light")}>
      <Sun className="hidden dark:block" />
      <Moon className="dark:hidden" />
    </Button>
  );
}

// One click into the high-contrast mode and back to the previous theme.
function ContrastToggle() {
  const { t } = useI18n();
  const { resolvedTheme, setTheme } = useTheme();
  const active = resolvedTheme === "contrast";
  const toggle = () => {
    if (active) {
      setTheme(localStorage.getItem("haushalt_theme_before_contrast") ?? "dark");
    } else {
      localStorage.setItem("haushalt_theme_before_contrast", resolvedTheme ?? "dark");
      setTheme("contrast");
    }
  };
  return (
    <Button variant="ghost" size="icon" aria-label={t("a11y.contrast")} aria-pressed={active} onClick={toggle} data-testid="contrast-toggle">
      <Eye />
    </Button>
  );
}

function ScanFab() {
  const { t } = useI18n();
  const { openCamera, busy } = useScan();
  return (
    <motion.button
      type="button"
      whileTap={{ scale: 0.92 }}
      onClick={openCamera}
      disabled={busy}
      aria-label={t("nav.scan")}
      className="-mt-7 flex size-14 items-center justify-center rounded-full bg-gradient-to-br from-primary to-chart-4 text-primary-foreground shadow-lg shadow-primary/40 disabled:opacity-60"
    >
      <Camera className="size-6" />
    </motion.button>
  );
}

function Shell({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const pathname = usePathname();
  const { openCamera, busy } = useScan();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);

  return (
    <div className="relative flex min-h-dvh flex-col">
      <div className="aurora" aria-hidden />
      <header className="sticky top-0 z-40 px-3 pt-[max(0.75rem,env(safe-area-inset-top))] md:px-6">
        <div className="glass mx-auto flex h-14 max-w-7xl items-center gap-2 rounded-2xl px-3">
          <Link href="/dashboard" aria-label={t("app.name")} className="flex shrink-0 items-center gap-2 pr-2 font-semibold tracking-tight">
            <span className="size-7 rounded-lg bg-gradient-to-br from-primary to-chart-4" aria-hidden />
            {/* the name gives way on narrow phones (large text in high contrast) */}
            <span className="text-gradient hidden text-lg min-[420px]:inline">{t("app.name")}</span>
          </Link>
          <nav className="hidden min-w-0 items-center gap-1 overflow-x-auto md:flex">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "relative rounded-lg px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground",
                  isActive(item.href) && "text-foreground",
                )}
              >
                {isActive(item.href) && (
                  <motion.span layoutId="nav-pill" className="absolute inset-0 -z-10 rounded-lg bg-accent" transition={{ type: "spring", stiffness: 400, damping: 34 }} />
                )}
                {t(item.label)}
              </Link>
            ))}
          </nav>
          <div className="ml-auto flex shrink-0 items-center gap-1">
            <button
              type="button"
              onClick={() => setPaletteOpen(true)}
              className="hidden h-8 items-center gap-2 rounded-lg border px-2.5 text-xs text-muted-foreground hover:text-foreground sm:flex"
              data-testid="palette-button"
              aria-label={`${t("common.search")} ⌘K`}
            >
              <Search className="size-3.5" />
              <span className="hidden xl:inline">{t("common.search")}</span>
              <kbd className="rounded border px-1 text-[10px]">⌘K</kbd>
            </button>
            <Button variant="ghost" size="icon" className="sm:hidden" aria-label={t("common.search")} onClick={() => setPaletteOpen(true)}>
              <Search />
            </Button>
            <Button size="sm" className="hidden md:inline-flex" onClick={openCamera} disabled={busy} aria-label={t("nav.scan")}>
              <Camera /> <span className="hidden xl:inline">{t("nav.scan")}</span>
            </Button>
            <LanguageToggle />
            <ContrastToggle />
            <ThemeToggle />
            <Button variant="ghost" size="icon" aria-label={t("nav.logout")} onClick={logout}>
              <LogOut />
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 px-3 pb-28 pt-4 md:px-6 md:pb-10">{children}</main>

      {/* phone: bottom tab bar with the camera in the middle */}
      <nav className="fixed inset-x-3 bottom-[max(0.75rem,env(safe-area-inset-bottom))] z-40 md:hidden" aria-label="Main">
        <div className="glass grid h-16 grid-cols-5 items-center rounded-2xl bg-background/90 px-1">
          {TABS.slice(0, 2).map((item) => (
            <TabLink key={item.href} href={item.href} label={t(item.label)} icon={item.icon} active={isActive(item.href)} />
          ))}
          <div className="flex justify-center">
            <ScanFab />
          </div>
          {TABS.slice(2).map((item) => (
            <TabLink key={item.href} href={item.href} label={t(item.label)} icon={item.icon} active={isActive(item.href)} />
          ))}
        </div>
      </nav>

      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </div>
  );
}

function TabLink({ href, label, icon: Icon, active }: { href: string; label: string; icon: typeof LayoutGrid; active: boolean }) {
  return (
    <Link href={href} className={cn("flex min-w-0 flex-col items-center gap-0.5 text-[10px] text-muted-foreground", active && "text-primary")}>
      <Icon className="size-5" />
      <span className="max-w-full truncate">{label}</span>
    </Link>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <ScanProvider>
      <Shell>{children}</Shell>
    </ScanProvider>
  );
}
