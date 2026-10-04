import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  catalog: vi.fn(),
  regions: vi.fn(),
  company: vi.fn(),
  listing: vi.fn(),
  photos: vi.fn(),
  requireSession: vi.fn()
}));

vi.mock("next/link", () => ({ default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a> }));
vi.mock("@/components/sell-form", () => ({ SellForm: (props: { makes: unknown[]; regions: unknown[]; initialListing?: { id: string } | null }) => createElement("div", { "data-makes": props.makes.length, "data-regions": props.regions.length, "data-listing-id": props.initialListing?.id || "" }) }));
vi.mock("@/lib/server-api", () => ({ serverApi: mocks }));
vi.mock("@/lib/server", () => ({ requireSession: mocks.requireSession }));

import SellPage from "./page";

describe("sell page catalog failures", () => {
  it("explains unavailable required reference data and leaves manual make entry available", async () => {
    mocks.requireSession.mockResolvedValue({ user: { display_name: "Тест" } });
    mocks.catalog.mockImplementation(async (kind: string) => {
      if (kind === "makes") throw new Error("catalog offline");
      return { items: [] };
    });
    mocks.regions.mockRejectedValueOnce(new Error("locations offline"));
    mocks.company.mockResolvedValue({ company: null });

    const html = renderToStaticMarkup(await SellPage({ searchParams: Promise.resolve({}) }));

    expect(html).toContain("Марку можно указать вручную");
    expect(html).toContain("отправить его на проверку получится после загрузки справочника");
    expect(html).toContain("data-makes=\"0\"");
    expect(html).toContain("data-regions=\"0\"");
    expect(html).toContain('href="/sell"');
  });

  it("loads an edit listing by ID even when it is beyond the first owner page", async () => {
    mocks.requireSession.mockResolvedValue({ user: { display_name: "Тест" } });
    mocks.catalog.mockResolvedValue({ items: [] });
    mocks.regions.mockResolvedValue({ items: [] });
    mocks.company.mockResolvedValue({ company: null });
    mocks.listing.mockResolvedValueOnce({ listing: {
      id: "listing-26",
      slug: "listing-26",
      title: "Audi A3",
      status: "draft",
      revision: 1,
      make: null,
      model: null,
      generation: null,
      year: null,
      mileage_km: null,
      fuel: null,
      transmission: null,
      drive: null,
      price: null,
      region: null,
      city: null,
      seller: { type: "company", id: "seller-1", name: "Тест" },
      created_at: "2026-09-28T00:00:00Z",
      damaged: false,
      parts_only: false,
      description: "",
      condition: null,
      photo_urls: []
    } });
    mocks.photos.mockResolvedValueOnce({ items: [] });

    const html = renderToStaticMarkup(await SellPage({ searchParams: Promise.resolve({ listing: "listing-26" }) }));

    expect(mocks.listing).toHaveBeenCalledWith("listing-26");
    expect(html).toContain('data-listing-id="listing-26"');
  });
});
