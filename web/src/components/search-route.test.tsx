import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/lib/api";
import { SearchRoute } from "@/components/search-route";
import { serverApi } from "@/lib/server-api";
import type { CatalogCity, CatalogItem, CatalogModification } from "@/lib/types";

const mocks = vi.hoisted(() => ({
  getSavedListingIds: vi.fn(async () => [] as string[]),
  redirect: vi.fn((href: string): never => { throw new Error(`REDIRECT:${href}`); })
}));

vi.mock("next/navigation", () => ({ redirect: mocks.redirect }));

vi.mock("@/lib/server-api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/server-api")>("@/lib/server-api");
  return { ...actual, getSavedListingIds: mocks.getSavedListingIds };
});

afterEach(() => {
  vi.restoreAllMocks();
  mocks.getSavedListingIds.mockReset();
  mocks.getSavedListingIds.mockResolvedValue([]);
});

describe("city search route", () => {
  it("loads city labels by region and passes them to the filter form", async () => {
    const regions: CatalogItem[] = [
      { id: "region-1", slug: "region-1", name: "Область 1" },
      { id: "region-2", slug: "region-2", name: "Область 2" }
    ];
    const city: CatalogItem = { id: "city-1", slug: "city-1", name: "Город 1" };
    const regionRequest = vi.spyOn(serverApi, "regions").mockResolvedValue({ items: regions });
    const cityRequest = vi.spyOn(serverApi, "cities").mockImplementation(async (regionId) => ({ items: regionId === "region-1" ? [city] : [] }));
    vi.spyOn(serverApi, "listings").mockResolvedValue({ items: [] });
    vi.spyOn(serverApi, "catalog").mockResolvedValue({ items: [] });

    const page = await SearchRoute({ search: { city_id: city.id }, title: "Автомобили в городе Город 1" });
    const results = page.props.children as ReactElement<{ cities: CatalogCity[] }>;

    expect(regionRequest).toHaveBeenCalledOnce();
    expect(cityRequest.mock.calls.map(([regionId]) => regionId)).toEqual(["region-1", "region-2"]);
    expect(results.props.cities).toEqual([{ ...city, region_id: "region-1" }]);
  });

  it("reuses cities already resolved for a city slug instead of loading them again", async () => {
    const city: CatalogCity = { id: "city-1", slug: "city-1", name: "Город 1", region_id: "region-1" };
    const regionRequest = vi.spyOn(serverApi, "regions").mockResolvedValue({ items: [] });
    const cityRequest = vi.spyOn(serverApi, "cities").mockResolvedValue({ items: [] });
    vi.spyOn(serverApi, "listings").mockResolvedValue({ items: [] });
    vi.spyOn(serverApi, "catalog").mockResolvedValue({ items: [] });

    const page = await SearchRoute({ search: { city_id: city.id }, title: "Город 1", initialCities: [city] });
    const results = page.props.children as ReactElement<{ cities: CatalogCity[] }>;

    expect(regionRequest).toHaveBeenCalledOnce();
    expect(cityRequest).not.toHaveBeenCalled();
    expect(results.props.cities).toEqual([city]);
  });

  it("marks search filters unavailable when a required catalog request fails", async () => {
    vi.spyOn(serverApi, "regions").mockResolvedValue({ items: [] });
    vi.spyOn(serverApi, "listings").mockResolvedValue({ items: [] });
    vi.spyOn(serverApi, "catalog").mockImplementation(async (kind) => {
      if (kind === "makes") throw new Error("catalog offline");
      return { items: [] };
    });

    const page = await SearchRoute({ search: {}, title: "Автомобили Беларуси" });
    const results = page.props.children as ReactElement<{ catalogsFailed: boolean }>;

    expect(results.props.catalogsFailed).toBe(true);
  });

  it("passes the signed-in user's saved IDs to search results", async () => {
    mocks.getSavedListingIds.mockResolvedValue(["listing-1"]);
    vi.spyOn(serverApi, "regions").mockResolvedValue({ items: [] });
    vi.spyOn(serverApi, "listings").mockResolvedValue({ items: [] });
    vi.spyOn(serverApi, "catalog").mockResolvedValue({ items: [] });

    const page = await SearchRoute({ search: {}, title: "Объявления" });
    const results = page.props.children as ReactElement<{ savedListingIds: string[] }>;

    expect(results.props.savedListingIds).toEqual(["listing-1"]);
  });

  it("loads modifications for the selected generation and passes them to search results", async () => {
    vi.spyOn(serverApi, "regions").mockResolvedValue({ items: [] });
    vi.spyOn(serverApi, "listings").mockResolvedValue({ items: [] });
    const modification: CatalogModification = { id: "mod-1", slug: "318i", name: "318i", generation_id: "generation-1", specs: null };
    const catalog = vi.spyOn(serverApi, "catalog").mockImplementation(async (kind, params = {}) => {
      if (kind === "modifications" && params.generation_id === "generation-1") return { items: [modification] };
      return { items: [] };
    });

    const page = await SearchRoute({ search: { generation_id: "generation-1" }, title: "BMW" });
    const results = page.props.children as ReactElement<{ modifications: CatalogModification[] }>;

    expect(catalog).toHaveBeenCalledWith("modifications", { generation_id: "generation-1" });
    expect(results.props.modifications).toEqual([modification]);
  });

  it("loads body variants for the selected generation and passes them to search results", async () => {
    vi.spyOn(serverApi, "regions").mockResolvedValue({ items: [] });
    const listings = vi.spyOn(serverApi, "listings").mockResolvedValue({ items: [] });
    const variant: CatalogItem = { id: "variant-1", slug: "sedan", name: "Седан", generation_id: "generation-1" };
    const catalog = vi.spyOn(serverApi, "catalog").mockImplementation(async (kind, params = {}) => {
      if (kind === "body-variants" && params.generation_id === "generation-1") return { items: [variant] };
      return { items: [] };
    });

    const page = await SearchRoute({
      search: { generation_id: "generation-1", body_variant_id: variant.id },
      title: "BMW"
    });
    const results = page.props.children as ReactElement<{ bodyVariants: CatalogItem[] }>;

    expect(catalog).toHaveBeenCalledWith("body-variants", { generation_id: "generation-1" });
    expect(listings).toHaveBeenCalledWith({
      generation_id: "generation-1",
      body_variant_id: variant.id,
      page_size: "25"
    });
    expect(results.props.bodyVariants).toEqual([variant]);
  });

  it("loads generations for the selected model and passes them to search results", async () => {
    vi.spyOn(serverApi, "regions").mockResolvedValue({ items: [] });
    vi.spyOn(serverApi, "listings").mockResolvedValue({ items: [] });
    const generation: CatalogItem = { id: "generation-1", slug: "m5-f90", name: "M5 F90", model_id: "model-1" };
    const catalog = vi.spyOn(serverApi, "catalog").mockImplementation(async (kind, params = {}) => {
      if (kind === "generations" && params.model_id === "model-1") return { items: [generation] };
      return { items: [] };
    });

    const page = await SearchRoute({ search: { model_id: "model-1", generation_id: generation.id }, title: "BMW M5" });
    const results = page.props.children as ReactElement<{ generations: CatalogItem[] }>;

    expect(catalog).toHaveBeenCalledWith("generations", { model_id: "model-1" });
    expect(results.props.generations).toEqual([generation]);
  });

  it("clears unavailable price filters and sorting while preserving other filters", async () => {
    vi.spyOn(serverApi, "regions").mockResolvedValue({ items: [] });
    vi.spyOn(serverApi, "listings").mockRejectedValue(new ApiClientError(422, {
      code: "exchange_rate_unavailable",
      message: "A fresh exchange rate is unavailable"
    }));
    vi.spyOn(serverApi, "catalog").mockResolvedValue({ items: [] });

    await expect(SearchRoute({
      search: { q: "BMW 3", price_min: "10000", sort: "price_asc", year_min: "2020", page: "3", currency: "BYN" },
      title: "Автомобили"
    })).rejects.toThrow("REDIRECT:/cars?q=BMW+3&currency=BYN&year_min=2020");
  });
});
