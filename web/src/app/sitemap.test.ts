import { beforeEach, describe, expect, it, vi } from "vitest";
import { SITE_ORIGIN } from "@/lib/site-config";

const mocks = vi.hoisted(() => ({ listings: vi.fn(), dealers: vi.fn() }));

vi.mock("@/lib/server-api", () => ({
  serverApi: { listings: mocks.listings, dealers: mocks.dealers },
}));

import sitemap from "@/app/sitemap";
import robots from "@/app/robots";

beforeEach(() => {
  mocks.listings.mockReset();
  mocks.dealers.mockReset();
});

function listing(id: string, overrides: Record<string, unknown> = {}) {
  return {
    id,
    slug: id,
    title: `Автомобиль ${id}`,
    make: { id: "make-1", slug: "bmw", name: "BMW" },
    model: { id: "model-1", slug: "3-series", name: "3 Series" },
    year: 2020,
    seller: { type: "private", id: "seller-1", name: "Продавец" },
    updated_at: "2026-09-28T12:00:00Z",
    city: { id: "city-1", slug: "minsk", name: "Минск" },
    ...overrides,
  };
}

function routedListing(id: string, makeSlug: string, modelSlug: string, citySlug: string, overrides: Record<string, unknown> = {}) {
  return listing(id, {
    make: { id: `make-${makeSlug}`, slug: makeSlug, name: makeSlug.toUpperCase() },
    model: { id: `model-${modelSlug}`, slug: modelSlug, name: modelSlug },
    city: { id: `city-${citySlug}`, slug: citySlug, name: citySlug },
    ...overrides,
  });
}

describe("closed pilot sitemap", () => {
  it("includes active listing routes and category routes only at their offer thresholds", async () => {
    const bmw = Array.from({ length: 3 }, (_, index) => routedListing(
      `bmw-${index + 1}`,
      "bmw",
      "3-series",
      "minsk",
      {
        updated_at: ["2026-09-27T08:00:00Z", "2026-09-29T10:00:00Z", "2026-09-28T09:00:00Z"][index],
        ...(index === 0 ? { seller: { type: "company", id: "dealer-1", name: "Дилер" } } : {}),
      },
    ));
    const audi = Array.from({ length: 7 }, (_, index) => routedListing(
      `audi-${index + 1}`,
      "audi",
      "a4",
      "minsk",
      index === 6 ? { updated_at: "2026-09-30T10:00:00Z" } : {},
    ));
    const honda = Array.from({ length: 9 }, (_, index) => routedListing(`honda-${index + 1}`, "honda", "civic", "brest"));
    const toyota = Array.from({ length: 2 }, (_, index) => routedListing(`toyota-${index + 1}`, "toyota", "corolla", "gomel"));
    const opel = Array.from({ length: 5 }, (_, index) => routedListing(`opel-${index + 1}`, "opel", "astra", "bobruisk"));
    const allListings = [
      ...bmw,
      ...audi,
      ...honda,
      ...toyota,
      ...opel,
      listing("manual-1", { make: null, model: null, city: null, updated_at: "not-a-date" }),
      routedListing("paused-1", "bmw", "3-series", "minsk", { status: "paused" }),
    ];
    mocks.listings.mockImplementation(async ({ page }: { page: string }) => ({
      items: allListings.slice((Number(page) - 1) * 25, Number(page) * 25),
      pagination: { page: Number(page), page_size: 25, total: allListings.length, pages: 2 },
    }));
    mocks.dealers.mockResolvedValue({
      items: [
        { id: "dealer-1", slug: "approved-dealer", status: "approved" },
        { id: "dealer-2", slug: "empty-dealer", status: "approved" },
      ],
      pagination: { page: 1, page_size: 25, total: 2, pages: 1 },
    });

    const entries = await sitemap();
    const urls = entries.map(({ url }) => url);
    const entriesByUrl = new Map(entries.map((entry) => [entry.url, entry]));

    expect(urls).toEqual(expect.arrayContaining([
      `${SITE_ORIGIN}/`,
      `${SITE_ORIGIN}/cars`,
      `${SITE_ORIGIN}/dealers`,
      `${SITE_ORIGIN}/cars/bmw`,
      `${SITE_ORIGIN}/cars/bmw/3-series`,
      `${SITE_ORIGIN}/cars/city/minsk`,
      `${SITE_ORIGIN}/cars/audi`,
      `${SITE_ORIGIN}/cars/audi/a4`,
      `${SITE_ORIGIN}/cars/honda`,
      `${SITE_ORIGIN}/cars/honda/civic`,
      `${SITE_ORIGIN}/cars/opel`,
      `${SITE_ORIGIN}/cars/opel/astra`,
      `${SITE_ORIGIN}/cars/bmw/3-series/bmw-1`,
      `${SITE_ORIGIN}/cars/manual-1/manual-1/manual-1`,
      `${SITE_ORIGIN}/dealers/approved-dealer`,
    ]));
    expect(urls).not.toContain(`${SITE_ORIGIN}/cars/toyota`);
    expect(urls).not.toContain(`${SITE_ORIGIN}/cars/toyota/corolla`);
    expect(urls).not.toContain(`${SITE_ORIGIN}/cars/city/brest`);
    expect(urls).not.toContain(`${SITE_ORIGIN}/cars/city/gomel`);
    expect(urls).not.toContain(`${SITE_ORIGIN}/cars/city/bobruisk`);
    expect(urls).not.toContain(`${SITE_ORIGIN}/cars/bmw/3-series/paused-1`);
    expect(urls).not.toContain(`${SITE_ORIGIN}/dealers/empty-dealer`);
    expect(entriesByUrl.get(`${SITE_ORIGIN}/cars/bmw/3-series/bmw-1`)?.lastModified).toEqual(new Date("2026-09-27T08:00:00Z"));
    expect(entriesByUrl.get(`${SITE_ORIGIN}/cars/bmw`)?.lastModified).toEqual(new Date("2026-09-29T10:00:00Z"));
    expect(entriesByUrl.get(`${SITE_ORIGIN}/cars/bmw/3-series`)?.lastModified).toEqual(new Date("2026-09-29T10:00:00Z"));
    expect(entriesByUrl.get(`${SITE_ORIGIN}/cars/city/minsk`)?.lastModified).toEqual(new Date("2026-09-30T10:00:00Z"));
    expect(entriesByUrl.get(`${SITE_ORIGIN}/`)).not.toHaveProperty("lastModified");
    expect(entriesByUrl.get(`${SITE_ORIGIN}/cars/manual-1/manual-1/manual-1`)).not.toHaveProperty("lastModified");
    expect(mocks.listings).toHaveBeenCalledTimes(2);
  });

  it("keeps its core routes available when the public catalog API is down", async () => {
    mocks.listings.mockRejectedValue(new Error("unavailable"));
    mocks.dealers.mockRejectedValue(new Error("unavailable"));

    const entries = await sitemap();
    const urls = entries.map(({ url }) => url);
    expect(urls).toEqual([`${SITE_ORIGIN}/`, `${SITE_ORIGIN}/cars`, `${SITE_ORIGIN}/dealers`]);
    expect(entries.every((entry) => !("lastModified" in entry))).toBe(true);
  });

  it("advertises the sitemap without weakening the API disallow rule", () => {
    expect(robots()).toEqual({
      rules: { userAgent: "*", disallow: "/api/v1/" },
      sitemap: `${SITE_ORIGIN}/sitemap.xml`,
    });
  });

});
