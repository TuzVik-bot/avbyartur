import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ getSessionServer: vi.fn() }));

vi.mock("@/components/auth-provider", () => ({ AuthProvider: ({ children }: { children: React.ReactNode }) => children }));
vi.mock("@/components/site-header", () => ({ SiteHeader: () => null }));
vi.mock("@/components/site-footer", () => ({ SiteFooter: () => null }));
vi.mock("@/lib/server-api", () => ({ getSessionServer: mocks.getSessionServer }));
vi.mock("next/font/local", () => ({ default: () => ({ className: "mock-font", variable: "--font-inter" }) }));

import RootLayout, { metadata } from "./layout";
import { SITE_NAME, SITE_ORIGIN } from "@/lib/site-config";

beforeEach(() => mocks.getSessionServer.mockResolvedValue(null));

describe("closed-pilot root layout", () => {
  it("provides a keyboard skip link and noindex metadata", async () => {
    const html = renderToStaticMarkup(await RootLayout({ children: createElement("h1", null, "Содержимое") }));

    expect(html).toContain('href="#main-content"');
    expect(html).toContain('id="main-content"');
    expect(html).toContain("Перейти к основному содержимому");
    expect(metadata.robots).toMatchObject({ index: false, follow: false, googleBot: { index: false, follow: false } });
    expect(metadata.metadataBase).toBeInstanceOf(URL);
    expect((metadata.metadataBase as URL).origin).toBe(SITE_ORIGIN);
    expect(metadata.title).toEqual({ default: `${SITE_NAME} — автомобили Беларуси`, template: `%s — ${SITE_NAME}` });
    expect(metadata.alternates?.canonical).toBeUndefined();
    expect(html).toContain('<html lang="ru">');
  });

  it("keeps the public shell available when session lookup is temporarily unavailable", async () => {
    mocks.getSessionServer.mockRejectedValueOnce(new Error("API unavailable"));

    const html = renderToStaticMarkup(await RootLayout({ children: createElement("h1", null, "Содержимое") }));

    expect(html).toContain("Содержимое");
  });
});
