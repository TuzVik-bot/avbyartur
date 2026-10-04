import { createElement, type ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CarsBySlugPage, { generateMetadata } from "@/app/cars/[...slug]/page";
import type { CatalogCity } from "@/lib/types";

const mocks = vi.hoisted(() => ({
  cities: vi.fn(),
  listings: vi.fn(),
  notFound: vi.fn((): never => { throw new Error("NEXT_NOT_FOUND"); }),
}));

vi.mock("next/navigation", () => ({
  notFound: mocks.notFound,
  redirect: vi.fn((href: string): never => { throw new Error(`REDIRECT:${href}`); })
}));

vi.mock("@/components/search-route", () => ({
  getCatalogCities: mocks.cities,
  SearchRoute: (props: { search: { city_id?: string; q?: string }; initialCities?: CatalogCity[]; title: string }) => createElement("section", {
    "data-city-id": props.search.city_id || "",
    "data-query": props.search.q || "",
    "data-initial-city-count": props.initialCities?.length || 0,
    "data-title": props.title
  })
}));

vi.mock("@/lib/server-api", () => ({ serverApi: { listings: mocks.listings } }));

const minsk: CatalogCity = { id: "city-minsk", slug: "minsk", name: "Минск", region_id: "minsk-city" };

beforeEach(() => {
  mocks.cities.mockReset();
  mocks.listings.mockReset();
  mocks.notFound.mockClear();
});

describe("city page route", () => {
  it("resolves a city slug into its catalog filter instead of a text query", async () => {
    mocks.cities.mockResolvedValue([minsk]);

    const page = await CarsBySlugPage({ params: Promise.resolve({ slug: ["city", "minsk"] }) });
    const pageTree = page as ReactElement<{ children: ReactElement<{
      search: { city_id?: string; q?: string };
      initialCities?: CatalogCity[];
      title: string;
    }> }>;
    const searchRoute = pageTree.props.children;

    expect(mocks.cities).toHaveBeenCalledOnce();
    expect(searchRoute.props).toMatchObject({
      search: { city_id: "city-minsk", page_size: "25" },
      initialCities: [minsk],
      title: "Автомобили в городе Минск"
    });
  });

  it("returns 404 for a city slug absent from the catalog", async () => {
    mocks.cities.mockResolvedValue([minsk]);

    await expect(CarsBySlugPage({ params: Promise.resolve({ slug: ["city", "unknown"] }) })).rejects.toThrow("NEXT_NOT_FOUND");
  });

  it("keeps a city indexable at exactly ten active offers", async () => {
    mocks.cities.mockResolvedValue([minsk]);
    mocks.listings.mockResolvedValue({ items: [], pagination: { page: 1, page_size: 1, total: 10, pages: 10 } });

    const metadata = await generateMetadata({ params: Promise.resolve({ slug: ["city", "minsk"] }) });

    expect(metadata.robots).toBeUndefined();
    expect(metadata.alternates?.canonical).toBe("https://suite-s1.denjik.by/cars/city/minsk");
    expect(mocks.listings).toHaveBeenCalledWith({ city_id: minsk.id, page_size: "1" });
  });

  it("noindexes a city below ten active offers", async () => {
    mocks.cities.mockResolvedValue([minsk]);
    mocks.listings.mockResolvedValue({ items: [], pagination: { page: 1, page_size: 1, total: 9, pages: 9 } });

    const metadata = await generateMetadata({ params: Promise.resolve({ slug: ["city", "minsk"] }) });

    expect(metadata.robots).toMatchObject({ index: false, follow: true });
  });

  it("fails closed for a city when its count is invalid or unavailable", async () => {
    mocks.cities.mockResolvedValue([minsk]);
    mocks.listings.mockResolvedValueOnce({ items: [], pagination: { page: 1, page_size: 1, total: Number.NaN, pages: 0 } })
      .mockRejectedValueOnce(new Error("offline"));

    const invalidCount = await generateMetadata({ params: Promise.resolve({ slug: ["city", "minsk"] }) });
    const unavailableCount = await generateMetadata({ params: Promise.resolve({ slug: ["city", "minsk"] }) });

    expect(invalidCount.robots).toMatchObject({ index: false, follow: true });
    expect(unavailableCount.robots).toMatchObject({ index: false, follow: true });
  });
});
