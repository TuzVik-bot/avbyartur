import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ getSessionServer: vi.fn() }));
const PUBLIC_INDEXING_ENV = "AVTORINOK_PUBLIC_INDEXING_ENABLED";

vi.mock("@/components/auth-provider", () => ({ AuthProvider: ({ children }: { children: React.ReactNode }) => children }));
vi.mock("@/components/site-header", () => ({ SiteHeader: () => null }));
vi.mock("@/components/site-footer", () => ({ SiteFooter: () => null }));
vi.mock("@/components/install-prompt", () => ({ InstallPrompt: () => <div data-install-prompt /> }));
vi.mock("@/components/compare-provider", () => ({ CompareProvider: ({ children }: { children: React.ReactNode }) => <div data-compare-provider>{children}</div> }));
vi.mock("@/lib/server-api", () => ({ getSessionServer: mocks.getSessionServer }));

import RootLayout, { metadata } from "./layout";
import { SITE_NAME, SITE_ORIGIN } from "@/lib/site-config";

beforeEach(() => mocks.getSessionServer.mockResolvedValue(null));
afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("closed-pilot root layout", () => {
  it("provides a keyboard skip link and keeps the closed pilot unindexable by default", async () => {
    const html = renderToStaticMarkup(await RootLayout({ children: createElement("h1", null, "Содержимое") }));

    expect(html).toContain('href="#main-content"');
    expect(html).toContain('id="main-content"');
    expect(html).toContain("data-compare-provider");
    expect(html).toContain("data-install-prompt");
    expect(html).toContain("Перейти к основному содержимому");
    expect(metadata.robots).toMatchObject({ index: false, follow: false, noarchive: true, googleBot: { index: false, follow: false, noimageindex: true } });
    expect(metadata.metadataBase).toBeInstanceOf(URL);
    expect((metadata.metadataBase as URL).origin).toBe(SITE_ORIGIN);
    expect(metadata.title).toEqual({ default: `${SITE_NAME} — автомобили Беларуси`, template: `%s — ${SITE_NAME}` });
    expect(metadata.description).toBe("Поиск автомобилей в Беларуси и подача объявлений в закрытом пилоте.");
    expect(metadata.appleWebApp).toMatchObject({ capable: true, statusBarStyle: "default", title: SITE_NAME });
    expect(metadata.alternates?.canonical).toBeUndefined();
    expect(html).toContain('<html lang="ru">');
    expect(html).toContain("application/ld+json");
  });

  it("switches to indexable metadata only when public indexing is enabled", async () => {
    vi.stubEnv(PUBLIC_INDEXING_ENV, "true");
    vi.resetModules();
    const publicLayout = await import("./layout");

    expect(publicLayout.metadata.robots).toEqual({ index: true, follow: true });
    expect(publicLayout.metadata.description).toBe("Каталог автомобилей с пробегом и новых в Беларуси: объявления от владельцев и дилеров, цены в BYN и USD, таможенный калькулятор и инструкции для покупателей.");
    expect(publicLayout.metadata.openGraph).toMatchObject({ siteName: SITE_NAME, images: [{ url: "/og-default.jpg" }] });
    expect(publicLayout.metadata.twitter).toMatchObject({ card: "summary_large_image" });
  });

  it("keeps the public shell available when session lookup is temporarily unavailable", async () => {
    mocks.getSessionServer.mockRejectedValueOnce(new Error("API unavailable"));

    const html = renderToStaticMarkup(await RootLayout({ children: createElement("h1", null, "Содержимое") }));

    expect(html).toContain("Содержимое");
  });
});
