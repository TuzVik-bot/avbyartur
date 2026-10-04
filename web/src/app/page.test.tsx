import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ListingSummary } from "@/lib/types";

const mocks = vi.hoisted(() => ({
  listings: vi.fn(),
  catalog: vi.fn(),
  getSavedListingIds: vi.fn(async () => [] as string[])
}));

vi.mock("@/lib/server-api", () => ({
  serverApi: { listings: mocks.listings, catalog: mocks.catalog },
  getSavedListingIds: mocks.getSavedListingIds
}));
vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a>
}));
vi.mock("next/image", () => ({
  default: ({ fill: _fill, sizes: _sizes, priority: _priority, ...props }: React.ImgHTMLAttributes<HTMLImageElement> & { fill?: boolean; sizes?: string; priority?: boolean }) => <img {...props} />
}));
vi.mock("@/components/listing-card", () => ({
  ListingCard: ({ listing, saved = false }: { listing: ListingSummary; saved?: boolean }) => <div data-listing-id={listing.id} data-favorite-saved={String(saved)} />
}));

import HomePage, { metadata } from "./page";

const listing: ListingSummary = {
  id: "listing-1",
  slug: "listing-1",
  title: "Марка Модель",
  make: { id: "make-1", slug: "marka", name: "Марка" },
  model: { id: "model-1", slug: "model", name: "Модель" },
  year: 2020,
  mileage_km: 50000,
  fuel: "petrol",
  transmission: "manual",
  drive: "front",
  price: { amount: "10000", currency: "BYN" },
  region: { id: "region-1", slug: "region", name: "Область" },
  city: { id: "city-1", slug: "minsk", name: "Минск" },
  seller: { id: "seller-1", type: "private", name: "Продавец" },
  created_at: "2026-09-27T00:00:00Z",
  updated_at: "2026-09-27T00:00:00Z",
  damaged: false,
  parts_only: false
};

beforeEach(() => {
  mocks.listings.mockResolvedValue({ items: [listing] });
  mocks.catalog.mockResolvedValue({ items: [] });
  mocks.getSavedListingIds.mockResolvedValue([]);
});

describe("home listing cards", () => {
  it("keeps the Russian canonical URL and declares its locale alternate", () => {
    expect(metadata.alternates).toEqual({
      canonical: "https://suite-s1.denjik.by/",
      languages: { ru: "https://suite-s1.denjik.by/" }
    });
  });

  it("marks saved listings as favorites", async () => {
    mocks.getSavedListingIds.mockResolvedValueOnce([listing.id]);

    const html = renderToStaticMarkup(await HomePage());

    expect(html).toContain('data-favorite-saved="true"');
  });
});
