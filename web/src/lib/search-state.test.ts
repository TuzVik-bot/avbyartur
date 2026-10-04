import { describe, expect, it } from "vitest";
import { activeSearchKeys, readSearchParams, searchUrl } from "@/lib/search-state";

describe("URL-backed listing filters", () => {
  it("reads only supported filters and takes the first repeated value", () => {
    const search = readSearchParams({ q: ["BMW 3", "ignored"], year_min: "2018", page: "2", modification_id: "mod-1", body_variant_id: "variant-1", unknown: "drop" });
    expect(search).toEqual({ q: "BMW 3", year_min: "2018", page: "2", modification_id: "mod-1", body_variant_id: "variant-1" });
  });

  it("preserves query state when changing pages and resets pagination when filters change", () => {
    const current = { q: "BMW 3", make_id: "make-1", modification_id: "mod-1", page: "3", sort: "price_asc" as const };
    expect(searchUrl(current, { page: "4" })).toBe("/cars?q=BMW+3&make_id=make-1&modification_id=mod-1&page=4&sort=price_asc");
    expect(searchUrl(current, { year_min: "2020" })).toBe("/cars?q=BMW+3&make_id=make-1&modification_id=mod-1&year_min=2020&sort=price_asc");
  });

  it("round-trips a body variant through the URL query", () => {
    const search = readSearchParams({ generation_id: "generation-1", body_variant_id: "variant-1" });
    const url = searchUrl(search, { page: "2" });

    expect(url).toBe("/cars?generation_id=generation-1&body_variant_id=variant-1&page=2");
    expect(readSearchParams(new URLSearchParams(url.split("?")[1]))).toEqual({
      generation_id: "generation-1",
      body_variant_id: "variant-1",
      page: "2"
    });
  });

  it("drops empty values instead of leaving stale query parameters", () => {
    expect(searchUrl({ q: "", page: "2", city_id: "city-1" }, { city_id: undefined })).toBe("/cars");
  });

  it("clears child filters when a parent filter chip is removed", () => {
    const search = readSearchParams({
      make_id: "make-1", model_id: "model-1", generation_id: "generation-1", modification_id: "mod-1",
      body_variant_id: "variant-1", region_id: "region-1", city_id: "city-1"
    });
    const paramsFor = (patch: Parameters<typeof searchUrl>[1]) => new URLSearchParams(searchUrl(search, patch).split("?")[1]);

    const afterMake = paramsFor({ make_id: undefined });
    expect(afterMake.has("make_id")).toBe(false);
    expect(afterMake.has("model_id")).toBe(false);
    expect(afterMake.has("generation_id")).toBe(false);
    expect(afterMake.has("modification_id")).toBe(false);
    expect(afterMake.has("body_variant_id")).toBe(false);

    const afterModel = paramsFor({ model_id: undefined });
    expect(afterModel.has("make_id")).toBe(true);
    expect(afterModel.has("model_id")).toBe(false);
    expect(afterModel.has("generation_id")).toBe(false);
    expect(afterModel.has("modification_id")).toBe(false);
    expect(afterModel.has("body_variant_id")).toBe(false);

    const afterGeneration = paramsFor({ generation_id: undefined });
    expect(afterGeneration.has("generation_id")).toBe(false);
    expect(afterGeneration.has("modification_id")).toBe(false);
    expect(afterGeneration.has("body_variant_id")).toBe(false);

    const afterRegion = paramsFor({ region_id: undefined });
    expect(afterRegion.has("region_id")).toBe(false);
    expect(afterRegion.has("city_id")).toBe(false);
  });

  it("does not expose fixed BYN currency as a removable filter", () => {
    expect(activeSearchKeys).not.toContain("currency");
  });

  it("round-trips repeated equipment codes and keeps the expanded listing filters", () => {
    const params = new URLSearchParams("equipment=abs&equipment=rear_camera&color=blue&customs_status=cleared_rb&power_min=150&has_vin=true");
    const search = readSearchParams(params);
    expect(search).toMatchObject({ equipment: ["abs", "rear_camera"], color: "blue", customs_status: "cleared_rb", power_min: "150", has_vin: "true" });
    expect(searchUrl(search)).toBe("/cars?color=blue&customs_status=cleared_rb&equipment=abs&equipment=rear_camera&has_vin=true&power_min=150");
  });
});
