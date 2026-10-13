import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/lib/api";

const mocks = vi.hoisted(() => ({
  listing: vi.fn(),
  favorites: vi.fn(),
  relatedListings: vi.fn(),
  session: vi.fn(),
  notFound: vi.fn((): never => { throw new Error("NEXT_NOT_FOUND"); }),
  redirect: vi.fn((href: string): never => { throw new Error(`REDIRECT:${href}`); })
}));

vi.mock("next/navigation", () => ({ notFound: mocks.notFound, redirect: mocks.redirect }));
vi.mock("next/link", () => ({ default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a> }));
vi.mock("@/lib/server-api", () => ({
  serverApi: { listing: mocks.listing, favorites: mocks.favorites, relatedListings: mocks.relatedListings },
  getSessionServer: mocks.session
}));
vi.mock("@/components/listing-detail", () => ({ ListingDetail: ({ listing }: { listing: { id: string } }) => createElement("div", { "data-listing-id": listing.id }) }));

import CategoryListingPage, { generateMetadata } from "@/app/[category]/[...slug]/page";

const params = { category: "trucks", slug: ["volvo-fh", "listing-1"] };
const truck = {
  id: "listing-1", slug: "volvo-fh", category_code: "trucks", title: "Volvo FH",
  make: null, model: null, year: 2020, mileage_km: 120000, city: null, manual_city: null,
  region: null, seller: { type: "private", id: "seller-1", name: "Продавец" },
  status: "active", description: "", price: null
};

beforeEach(() => {
  mocks.listing.mockReset();
  mocks.favorites.mockReset();
  mocks.relatedListings.mockReset().mockResolvedValue({ items: [] });
  mocks.session.mockReset().mockResolvedValue(null);
  mocks.notFound.mockClear();
  mocks.redirect.mockClear();
});

describe("non-car listing detail route", () => {
  it("uses the category-aware canonical and renders the listing", async () => {
    mocks.listing.mockResolvedValue({ listing: truck });

    const metadata = await generateMetadata({ params: Promise.resolve(params) });
    const html = renderToStaticMarkup(await CategoryListingPage({ params: Promise.resolve(params) }));

    expect(metadata.alternates?.canonical).toBe("https://suite-s1.denjik.by/trucks/volvo-fh/listing-1");
    expect(html).toContain('data-listing-id="listing-1"');
    expect(mocks.redirect).not.toHaveBeenCalled();
  });

  it("does not render a listing under a different category", async () => {
    mocks.listing.mockResolvedValue({ listing: { ...truck, category_code: "buses" } });

    await expect(CategoryListingPage({ params: Promise.resolve(params) })).rejects.toThrow("NEXT_NOT_FOUND");
  });

  it("keeps a removed listing linked to its category search", async () => {
    mocks.listing.mockRejectedValue(new ApiClientError(410, { code: "gone", message: "Снято" }));

    const html = renderToStaticMarkup(await CategoryListingPage({ params: Promise.resolve(params) }));

    expect(html).toContain("Объявление снято с публикации");
    expect(html).toContain('href="/trucks"');
  });
});
