import type { Metadata, Viewport } from "next";
import { cookies, headers } from "next/headers";
import { ThemeProvider } from "next-themes";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { I18nProvider } from "@/lib/i18n/provider";
import { isLocale, negotiate } from "@/lib/i18n/messages";
import { LOCALE_COOKIE } from "@/lib/session";
import "./globals.css";

export const metadata: Metadata = {
  title: "Haushalt",
  description: "Household spending at a glance",
  applicationName: "Haushalt",
  appleWebApp: { capable: true, title: "Haushalt", statusBarStyle: "black-translucent" },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f7f7fb" },
    { media: "(prefers-color-scheme: dark)", color: "#14121f" },
  ],
  viewportFit: "cover",
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  const cookie = (await cookies()).get(LOCALE_COOKIE)?.value;
  const locale = isLocale(cookie) ? cookie : negotiate((await headers()).get("accept-language"));
  return (
    // next-themes sets the class on <html> before hydration
    <html lang={locale} className="h-full antialiased" suppressHydrationWarning>
      <body className="min-h-full flex flex-col">
        <ThemeProvider attribute="class" defaultTheme="dark" enableSystem disableTransitionOnChange>
          <I18nProvider initialLocale={locale}>
            <TooltipProvider>{children}</TooltipProvider>
            <Toaster richColors closeButton position="top-center" />
          </I18nProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
