import { describe, expect, it } from "vitest";
import { buildUseCaseSearchHref, type UseCaseFilterState, type UseCasePreset, useCasePresets } from "@/lib/use-case-presets";

function stateFor(preset: UseCasePreset, overrides: Partial<UseCaseFilterState> = {}): UseCaseFilterState {
  return {
    categoryCode: preset.defaults.category_code || "",
    condition: preset.defaults.condition || "",
    fuel: preset.defaults.fuel || "",
    hasPhotos: preset.defaults.has_photos === "true",
    yearFrom: "",
    priceTo: "",
    ...overrides,
  };
}

function presetFor(slug: string): UseCasePreset {
  const preset = useCasePresets.find((item) => item.slug === slug);
  if (!preset) throw new Error(`Missing preset: ${slug}`);
  return preset;
}

describe("use case search presets", () => {
  it("starts from valid, scenario-specific public catalog filters", () => {
    expect(useCasePresets.map((preset) => buildUseCaseSearchHref(preset, stateFor(preset)))).toEqual([
      "/cars?category_code=cars&condition=used",
      "/cars?category_code=cars&has_photos=true",
      "/cars?category_code=cars&fuel=electric",
      "/cars?category_code=trucks",
    ]);
  });

  it("rebuilds the existing catalog URL from user-edited category and limits", () => {
    const preset = presetFor("first-car");
    expect(buildUseCaseSearchHref(preset, stateFor(preset, {
      categoryCode: "trucks",
      condition: "new",
      yearFrom: "2018",
      priceTo: "25000",
    }))).toBe("/cars?category_code=trucks&price_max=25000&currency=BYN&year_min=2018&condition=new");
  });

  it("omits invalid numeric values and removes an unchecked photo filter", () => {
    const preset = presetFor("family");
    expect(buildUseCaseSearchHref(preset, stateFor(preset, {
      hasPhotos: false,
      yearFrom: "1885",
      priceTo: "-1",
    }))).toBe("/cars?category_code=cars");
  });

  it("does not turn an unknown category into a search constraint", () => {
    const preset = presetFor("first-car");
    expect(buildUseCaseSearchHref(preset, stateFor(preset, { categoryCode: "not-a-category" })))
      .toBe("/cars?condition=used");
  });
});
