import type { Metadata, Viewport } from "next";
import { AuthProvider } from "@/components/auth-provider";
import { CompareProvider } from "@/components/compare-provider";
import { GlobalCompareTray } from "@/components/compare-button";
import { ContactClickConsentProvider } from "@/components/contact-click-consent";
import { MeasurementProvider } from "@/components/measurement-provider";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { InstallPrompt } from "@/components/install-prompt";
import { DEFAULT_LOCALE, getMessage } from "@/lib/i18n";
import { isPublicIndexingEnabled, rootRobots } from "@/lib/pilot-visibility";
import { buildOrganizationJsonLd, buildWebsiteJsonLd, serializeJsonLd } from "@/lib/seo";
import { getSessionServer } from "@/lib/server-api";
import { SITE_NAME, SITE_ORIGIN } from "@/lib/site-config";
import { THEME_INIT_SCRIPT } from "@/lib/theme";
import "./globals.css";

export const dynamic = "force-dynamic";

const layoutDescription = getMessage(
  isPublicIndexingEnabled() ? "layout.descriptionPublic" : "layout.description",
  DEFAULT_LOCALE,
);

const verification: Metadata["verification"] = {
  ...(process.env.GOOGLE_SITE_VERIFICATION ? { google: process.env.GOOGLE_SITE_VERIFICATION } : {}),
  ...(process.env.YANDEX_SITE_VERIFICATION ? { yandex: process.env.YANDEX_SITE_VERIFICATION } : {}),
};

export const metadata: Metadata = {
  metadataBase: new URL(SITE_ORIGIN),
  title: { default: `${SITE_NAME} — ${getMessage("layout.titleSuffix", DEFAULT_LOCALE)}`, template: `%s — ${SITE_NAME}` },
  description: layoutDescription,
  robots: rootRobots(),
  applicationName: SITE_NAME,
  appleWebApp: { capable: true, statusBarStyle: "default", title: SITE_NAME },
  referrer: "strict-origin-when-cross-origin",
  openGraph: {
    type: "website",
    siteName: SITE_NAME,
    locale: DEFAULT_LOCALE,
    url: SITE_ORIGIN,
    title: `${SITE_NAME} — ${getMessage("layout.titleSuffix", DEFAULT_LOCALE)}`,
    description: layoutDescription,
    images: [{ url: "/og-default.jpg", width: 1200, height: 630, alt: SITE_NAME }],
  },
  twitter: {
    card: "summary_large_image",
    title: `${SITE_NAME} — ${getMessage("layout.titleSuffix", DEFAULT_LOCALE)}`,
    description: layoutDescription,
    images: ["/og-default.jpg"],
  },
  ...(Object.keys(verification).length ? { verification } : {}),
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // Keep public pages available if the API is temporarily offline. Protected
  // route guards call the same lookup without swallowing service failures.
  const initialSession = await getSessionServer().catch(() => null);
  return (
    <html lang={DEFAULT_LOCALE} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body>
        <AuthProvider initialSession={initialSession}>
          <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: serializeJsonLd(buildWebsiteJsonLd()) }} />
          <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: serializeJsonLd(buildOrganizationJsonLd()) }} />
          <ContactClickConsentProvider><MeasurementProvider><CompareProvider>
            <a className="skip-link" href="#main-content">{getMessage("layout.skipToMainContent", DEFAULT_LOCALE)}</a>
            <SiteHeader />
            <main id="main-content">{children}</main>
            <SiteFooter />
            <InstallPrompt />
            <GlobalCompareTray />
          </CompareProvider></MeasurementProvider></ContactClickConsentProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
