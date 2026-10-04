import type { Metadata, Viewport } from "next";
import { AuthProvider } from "@/components/auth-provider";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { DEFAULT_LOCALE, getMessage } from "@/lib/i18n";
import { getSessionServer } from "@/lib/server-api";
import { SITE_NAME, SITE_ORIGIN } from "@/lib/site-config";
import "./globals.css";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_ORIGIN),
  title: { default: `${SITE_NAME} — ${getMessage("layout.titleSuffix", DEFAULT_LOCALE)}`, template: `%s — ${SITE_NAME}` },
  description: getMessage("layout.description", DEFAULT_LOCALE),
  robots: { index: false, follow: false, noarchive: true, googleBot: { index: false, follow: false, noimageindex: true } },
  applicationName: SITE_NAME,
  referrer: "strict-origin-when-cross-origin"
};

export const viewport: Viewport = { themeColor: "#f4f6f5", width: "device-width", initialScale: 1 };

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // Keep public pages available if the API is temporarily offline. Protected
  // route guards call the same lookup without swallowing service failures.
  const initialSession = await getSessionServer().catch(() => null);
  return (
    <html lang={DEFAULT_LOCALE}>
      <body>
        <AuthProvider initialSession={initialSession}>
          <a className="skip-link" href="#main-content">{getMessage("layout.skipToMainContent", DEFAULT_LOCALE)}</a>
          <SiteHeader />
          <main id="main-content">{children}</main>
          <SiteFooter />
        </AuthProvider>
      </body>
    </html>
  );
}
