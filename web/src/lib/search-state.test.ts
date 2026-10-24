import { describe, expect, it } from "vitest";
import { searchPath } from "@/lib/api";
import { activeSearchKeys, clearSearchFilters, readSearchParams, searchRelaxationOptions, searchUrl } from "@/lib/search-state";
import { getListingSubcategories, isListingSubcategory, listingSubcategoryDetailsField } from "@/lib/listing-subcategories";

describe("URL-backed listing filters", () => {
  it("reads only supported filters and takes the first repeated value", () => {
    const search = readSearchParams({ q: ["BMW 3", "ignored"], year_min: "2018", page: "2", modification_id: "mod-1", body_variant_id: "variant-1", unknown: "drop" });
    expect(search).toEqual({ q: "BMW 3", year_min: "2018", page: "2", modification_id: "mod-1", body_variant_id: "variant-1" });
  });

  it("adds the UI default currency to price-filter API requests only when currency is missing", () => {
    const missingCurrency = readSearchParams(new URLSearchParams("q=BMW&price_min=10000&year_min=2020&page=3"));
    const defaultedParams = new URLSearchParams(searchPath({ ...missingCurrency, page_size: "25" }).split("?")[1]);
    expect(Object.fromEntries(defaultedParams)).toEqual({
      q: "BMW",
      price_min: "10000",
      currency: "BYN",
      year_min: "2020",
      page: "3",
      page_size: "25"
    });

    const explicitUsd = readSearchParams(new URLSearchParams("price_max=12000&currency=USD"));
    expect(searchPath(explicitUsd)).toContain("currency=USD");

    const unsupportedCurrency = readSearchParams(new URLSearchParams("price_min=10000&currency=EUR"));
    expect(unsupportedCurrency.currency).toBe("EUR");
    expect(searchPath(unsupportedCurrency)).toContain("currency=EUR");
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

  it("reads valid category codes and drops unsupported values", () => {
    expect(readSearchParams(new URLSearchParams("category_code=parts"))).toEqual({ category_code: "parts" });
    expect(readSearchParams({ category_code: "aircraft" })).toEqual({});
  });

  it("preserves category codes in canonical URLs without exposing them as filter chips", () => {
    const search = readSearchParams(new URLSearchParams("page=2&q=tires&category_code=parts"));

    expect(searchUrl(search)).toBe("/cars?category_code=parts&q=tires&page=2");
    expect(readSearchParams(new URLSearchParams(searchUrl(search).split("?")[1]))).toEqual(search);
    expect(activeSearchKeys).not.toContain("category_code");
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

  it("suggests removing one active filter while preserving the rest of the search", () => {
    const search = readSearchParams(new URLSearchParams(
      "category_code=cars&q=BMW&make_id=make-1&model_id=model-1&price_max=12000&city_id=minsk&page=3&currency=BYN&sort=price_asc"
    ));
    const options = searchRelaxationOptions(search, 3);

    expect(options.map(({ key }) => key)).toEqual(["city_id", "price_max", "model_id"]);
    expect(options[0].href).toBe("/cars?category_code=cars&q=BMW&make_id=make-1&model_id=model-1&price_max=12000&currency=BYN&sort=price_asc");
    expect(options[1].href).toBe("/cars?category_code=cars&q=BMW&make_id=make-1&model_id=model-1&currency=BYN&city_id=minsk&sort=price_asc");
    expect(options[2].href).toBe("/cars?category_code=cars&q=BMW&make_id=make-1&price_max=12000&currency=BYN&city_id=minsk&sort=price_asc");
  });

  it("keeps category, currency, vehicle match, and both price bounds when relaxing location", () => {
    const search = readSearchParams(new URLSearchParams(
      "category_code=cars&make_id=make-1&model_id=model-1&price_min=8000&price_max=12000&currency=USD&city_id=minsk"
    ));
    const [locationOption] = searchRelaxationOptions(search, 1);
    const params = new URLSearchParams(locationOption.href.split("?")[1]);

    expect(params.get("category_code")).toBe("cars");
    expect(params.get("currency")).toBe("USD");
    expect(params.get("make_id")).toBe("make-1");
    expect(params.get("model_id")).toBe("model-1");
    expect(params.get("price_min")).toBe("8000");
    expect(params.get("price_max")).toBe("12000");
    expect(params.has("city_id")).toBe(false);
  });

  it("offers a 15 percent budget expansion while preserving the rest of the search", () => {
    const search = readSearchParams(new URLSearchParams(
      "category_code=cars&q=BMW&make_id=make-1&model_id=model-1&price_min=8000&price_max=12000&currency=USD&city_id=minsk&page=3&sort=price_asc"
    ));
    const budgetOption = searchRelaxationOptions(search, 8, true).find(({ key }) => key === "budget");
    expect(budgetOption?.label).toBe("Расширить бюджет на 15%");

    const params = new URLSearchParams(budgetOption?.href.split("?")[1]);
    expect(params.get("category_code")).toBe("cars");
    expect(params.get("q")).toBe("BMW");
    expect(params.get("make_id")).toBe("make-1");
    expect(params.get("model_id")).toBe("model-1");
    expect(params.get("price_min")).toBe("6800");
    expect(params.get("price_max")).toBe("13800");
    expect(params.get("currency")).toBe("USD");
    expect(params.get("city_id")).toBe("minsk");
    expect(params.get("sort")).toBe("price_asc");
    expect(params.has("page")).toBe(false);
  });

  it("does not offer budget expansion for invalid prices, unsupported currency, or unavailable FX", () => {
    const validSearch = { price_min: "8000", price_max: "12000", currency: "BYN" } as const;
    expect(searchRelaxationOptions(validSearch, 8, false).some(({ key }) => key === "budget")).toBe(false);
    expect(searchRelaxationOptions({ ...validSearch, price_min: "0" }, 8, true).some(({ key }) => key === "budget")).toBe(false);
    expect(searchRelaxationOptions({ ...validSearch, price_max: "-1" }, 8, true).some(({ key }) => key === "budget")).toBe(false);
    expect(searchRelaxationOptions({ ...validSearch, currency: "EUR" }, 8, true).some(({ key }) => key === "budget")).toBe(false);
    expect(searchRelaxationOptions({ price_max: "12000" }, 8, true).some(({ key }) => key === "budget")).toBe(false);
    expect(searchRelaxationOptions({ ...validSearch, price_min: "20000", price_max: "10000" }, 8, true).some(({ key }) => key === "budget")).toBe(false);
  });

  it("widens only the positive price bounds that are present", () => {
    const lowerOnly = searchRelaxationOptions({ price_min: "1000", currency: "BYN" }, 8, true).find(({ key }) => key === "budget");
    const lowerParams = new URLSearchParams(lowerOnly?.href.split("?")[1]);
    expect(lowerParams.get("price_min")).toBe("850");
    expect(lowerParams.has("price_max")).toBe(false);

    const upperOnly = searchRelaxationOptions({ price_max: "1000", currency: "BYN" }, 8, true).find(({ key }) => key === "budget");
    const upperParams = new URLSearchParams(upperOnly?.href.split("?")[1]);
    expect(upperParams.has("price_min")).toBe(false);
    expect(upperParams.get("price_max")).toBe("1150");
  });

  it("keeps relaxation links unique when a budget expansion is available", () => {
    const options = searchRelaxationOptions({ price_min: "8000", price_max: "12000", currency: "BYN", city_id: "minsk" }, 8, true);
    expect(new Set(options.map(({ href }) => href)).size).toBe(options.length);
  });

  it("keeps category and sort while clearing filters for the full reset action", () => {
    const search = readSearchParams(new URLSearchParams(
      "category_code=parts&q=tires&make_id=make-1&city_id=minsk&page=2&currency=BYN&sort=newest"
    ));

    expect(clearSearchFilters(search)).toBe("/cars?category_code=parts&currency=BYN&sort=newest");
  });

  it("has no relaxation options when only presentation state is selected", () => {
    expect(searchRelaxationOptions({ category_code: "parts", page: "2", sort: "newest", currency: "BYN" })).toEqual([]);
  });

  it("round-trips repeated equipment codes and keeps the expanded listing filters", () => {
    const params = new URLSearchParams("equipment=abs&equipment=rear_camera&color=blue&customs_status=cleared_rb&power_min=150&has_vin=true");
    const search = readSearchParams(params);
    expect(search).toMatchObject({ equipment: ["abs", "rear_camera"], color: "blue", customs_status: "cleared_rb", power_min: "150", has_vin: "true" });
    expect(searchUrl(search)).toBe("/cars?color=blue&customs_status=cleared_rb&equipment=abs&equipment=rear_camera&has_vin=true&power_min=150");
  });
});
describe("listing subcategories", () => {
  it("round-trips stable slugs and clears them when the parent category changes", () => {
    const parsed = readSearchParams(new URLSearchParams("category_code=watercraft&subcategory=jet_ski"));
    expect(parsed.subcategory).toBe("jet_ski");
    expect(searchUrl(parsed)).toContain("subcategory=jet_ski");
    expect(searchUrl(parsed, { category_code: "motorcycles" })).not.toContain("subcategory=");
    expect(isListingSubcategory("watercraft", "jet_ski")).toBe(true);
    expect(isListingSubcategory("watercraft", "tractor")).toBe(false);
    expect(readSearchParams(new URLSearchParams("category_code=watercraft&subcategory=tractor")).subcategory).toBeUndefined();
  });

  it("exposes requested categories without inventing wheels subcategories", () => {
    expect(getListingSubcategories("agricultural_equipment").map(({ value }) => value)).toContain("grain_harvest");
    expect(getListingSubcategories("tires").map(({ value }) => value)).toEqual(["passenger", "truck", "motorcycle"]);
    expect(getListingSubcategories("wheels")).toEqual([]);
    expect(listingSubcategoryDetailsField("special_equipment")).toBe("equipment_type");
  });
});
