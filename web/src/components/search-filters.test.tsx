import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SearchFilters } from "@/components/search-filters";
import { api } from "@/lib/api";
import type { CatalogCity, CatalogItem, CatalogModification } from "@/lib/types";

const makeA: CatalogItem = { id: "make-a", slug: "make-a", name: "Марка A" };
const makeB: CatalogItem = { id: "make-b", slug: "make-b", name: "Марка B" };
const modelA: CatalogItem = { id: "model-a", slug: "model-a", name: "Модель A", make_id: makeA.id };
const modelB: CatalogItem = { id: "model-b", slug: "model-b", name: "Модель B", make_id: makeB.id };
const generationA: CatalogItem = { id: "generation-a", slug: "generation-a", name: "Поколение A", model_id: modelA.id };
const generationB: CatalogItem = { id: "generation-b", slug: "generation-b", name: "Поколение B", model_id: modelB.id };
const generationNext: CatalogItem = { id: "generation-next", slug: "generation-next", name: "Поколение A+", model_id: modelA.id };
const modificationA: CatalogModification = { id: "modification-a", slug: "modification-a", name: "Двигатель A", generation_id: generationA.id, specs: null };
const modificationNext: CatalogModification = { id: "modification-next", slug: "modification-next", name: "Двигатель A+", generation_id: generationNext.id, specs: null };
const regionA: CatalogItem = { id: "region-a", slug: "region-a", name: "Область A" };
const regionB: CatalogItem = { id: "region-b", slug: "region-b", name: "Область B" };
const cityA: CatalogCity = { id: "city-a", slug: "city-a", name: "Город A", region_id: "region-a" };
const cityB: CatalogCity = { id: "city-b", slug: "city-b", name: "Город B", region_id: "region-b" };

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

function choose(name: string, value: string) {
  const select = container.querySelector<HTMLSelectElement>(`select[name="${name}"]`);
  if (!select) throw new Error(`Missing select: ${name}`);
  select.value = value;
  select.dispatchEvent(new Event("change", { bubbles: true }));
}

describe("search filter dependencies", () => {
  it("preserves selected catalog IDs when option catalog requests fail temporarily", async () => {
    vi.spyOn(api, "catalog").mockRejectedValue(new Error("catalog temporarily unavailable"));
    vi.spyOn(api, "cities").mockRejectedValue(new Error("cities temporarily unavailable"));

    await act(async () => {
      root.render(createElement(SearchFilters, {
        search: {
          make_id: makeA.id,
          model_id: modelA.id,
          generation_id: generationA.id,
          body_variant_id: "variant-a",
          modification_id: modificationA.id,
          body_type: "sedan",
          region_id: regionA.id,
          city_id: cityA.id
        },
        makes: [],
        initialModels: [],
        regions: [],
        initialCities: [],
        bodyTypes: []
      }));
      await Promise.resolve();
    });

    const submitted = new FormData(container.querySelector<HTMLFormElement>("form")!);
    expect(submitted.get("make_id")).toBe(makeA.id);
    expect(submitted.get("model_id")).toBe(modelA.id);
    expect(submitted.get("generation_id")).toBe(generationA.id);
    expect(submitted.get("body_variant_id")).toBe("variant-a");
    expect(submitted.get("modification_id")).toBe(modificationA.id);
    expect(submitted.get("body_type")).toBe("sedan");
    expect(submitted.get("region_id")).toBe(regionA.id);
    expect(submitted.get("city_id")).toBe(cityA.id);
  });

  it("resets uncontrolled fields when browser navigation changes the URL state", async () => {
    const props = {
      makes: [],
      initialModels: [],
      regions: [],
      initialCities: [],
      bodyTypes: [{ id: "wagon-id", slug: "wagon", name: "Универсал" }]
    };
    await act(async () => {
      root.render(createElement(SearchFilters, {
        ...props,
        search: { price_min: "10000", body_type: "wagon", damaged: "true" }
      }));
    });
    expect(container.querySelector<HTMLInputElement>('input[name="price_min"]')?.value).toBe("10000");
    expect(container.querySelector<HTMLSelectElement>('select[name="body_type"]')?.value).toBe("wagon");
    expect(container.querySelector<HTMLInputElement>('input[name="damaged"]')?.checked).toBe(true);

    await act(async () => {
      root.render(createElement(SearchFilters, { ...props, search: {} }));
    });
    expect(container.querySelector<HTMLInputElement>('input[name="price_min"]')?.value).toBe("");
    expect(container.querySelector<HTMLSelectElement>('select[name="body_type"]')?.value).toBe("");
    expect(container.querySelector<HTMLInputElement>('input[name="damaged"]')?.checked).toBe(false);
  });

  it("disables price filtering when the official exchange rate is stale", async () => {
    await act(async () => {
      root.render(createElement(SearchFilters, {
        search: {},
        makes: [],
        initialModels: [],
        regions: [],
        initialCities: [],
        bodyTypes: [],
        priceOperationsAvailable: false
      }));
    });

    const priceGroup = [...container.querySelectorAll("fieldset")]
      .find((fieldset) => fieldset.querySelector("legend")?.textContent === "Цена, BYN") as HTMLFieldSetElement | undefined;
    expect(priceGroup?.disabled).toBe(true);
    expect(container.querySelector<HTMLInputElement>('input[name="year_min"]')?.disabled).toBe(false);
  });

  it("keeps the extended seller fields, feature toggles, and repeated equipment selections", async () => {
    await act(async () => {
      root.render(createElement(SearchFilters, {
        search: { color: "blue", customs_status: "cleared_rb", technical_condition: "good", body_condition: "repaired", exchange: "true", credit: "true", equipment: ["abs", "rear_camera"], district: "Центральный", has_vin: "true", engine_volume_min: "1.6", power_max: "180" },
        makes: [], initialModels: [], regions: [], initialCities: [], bodyTypes: []
      }));
    });
    const submitted = new FormData(container.querySelector<HTMLFormElement>("form")!);
    expect(submitted.get("color")).toBe("blue");
    expect(submitted.get("customs_status")).toBe("cleared_rb");
    expect(submitted.get("technical_condition")).toBe("good");
    expect(submitted.get("body_condition")).toBe("repaired");
    expect(submitted.get("exchange")).toBe("true");
    expect(submitted.get("credit")).toBe("true");
    expect(submitted.getAll("equipment")).toEqual(["abs", "rear_camera"]);
    expect(submitted.get("district")).toBe("Центральный");
    expect(submitted.get("has_vin")).toBe("true");
    expect(submitted.get("engine_volume_min")).toBe("1.6");
    expect(submitted.get("power_max")).toBe("180");
  });

  it("restores the city and its region when navigating from a broad search", async () => {
    await act(async () => {
      root.render(createElement(SearchFilters, {
        search: {},
        makes: [],
        initialModels: [],
        regions: [regionA],
        initialCities: [],
        bodyTypes: []
      }));
    });

    await act(async () => {
      root.render(createElement(SearchFilters, {
        search: { city_id: cityA.id },
        makes: [],
        initialModels: [],
        regions: [regionA],
        initialCities: [cityA],
        bodyTypes: []
      }));
    });

    const citySelect = container.querySelector<HTMLSelectElement>('select[name="city_id"]');
    expect(citySelect?.disabled).toBe(false);
    expect(citySelect?.value).toBe(cityA.id);
    const regionSelect = container.querySelector<HTMLSelectElement>('select[name="region_id"]');
    expect(regionSelect?.value).toBe(regionA.id);
    expect(new FormData(container.querySelector("form")!).get("city_id")).toBe(cityA.id);
    expect(new FormData(container.querySelector("form")!).get("region_id")).toBe(regionA.id);

    const toggle = container.querySelector<HTMLButtonElement>(".filter-toggle");
    expect(toggle?.getAttribute("aria-controls")).toBe("search-filter-panel");
    expect(container.querySelector("#search-filter-panel")).not.toBeNull();
  });

  it("reloads dependent catalogs, clears incompatible values, and submits the new IDs", async () => {
    const catalog = vi.spyOn(api, "catalog").mockImplementation(async (kind, params = {}) => {
      if (kind === "models" && params.make_id === makeB.id) return { items: [modelB] };
      if (kind === "generations" && params.model_id === modelA.id) return { items: [generationA] };
      if (kind === "generations" && params.model_id === modelB.id) return { items: [generationB] };
      return { items: [] };
    });
    const cities = vi.spyOn(api, "cities").mockResolvedValue({ items: [cityB] });

    await act(async () => {
      root.render(createElement(SearchFilters, {
        search: { q: "BMW 3", make_id: makeA.id, model_id: modelA.id, generation_id: generationA.id, region_id: regionA.id, city_id: cityA.id, sort: "price_asc" },
        makes: [makeA, makeB],
        initialModels: [modelA],
        regions: [regionA, regionB],
        initialCities: [cityA],
        bodyTypes: [{ id: "sedan-id", slug: "sedan", name: "Седан" }]
      }));
    });

    await act(async () => { await Promise.resolve(); });
    await act(async () => {
      choose("make_id", makeB.id);
      await Promise.resolve();
    });
    expect(catalog).toHaveBeenCalledWith("models", { make_id: makeB.id });
    expect(container.querySelector<HTMLSelectElement>('select[name="model_id"]')?.value).toBe("");
    expect(container.querySelector<HTMLSelectElement>('select[name="generation_id"]')?.value).toBe("");
    expect(container.querySelector('select[name="model_id"] option[value="model-b"]')).not.toBeNull();

    await act(async () => {
      choose("model_id", modelB.id);
      await Promise.resolve();
    });
    expect(catalog).toHaveBeenCalledWith("generations", { model_id: modelB.id });
    expect(container.querySelector('select[name="generation_id"] option[value="generation-b"]')).not.toBeNull();
    await act(async () => { choose("generation_id", generationB.id); });

    await act(async () => {
      choose("region_id", regionB.id);
      await Promise.resolve();
    });
    expect(cities).toHaveBeenCalledWith(regionB.id);
    expect(container.querySelector<HTMLSelectElement>('select[name="city_id"]')?.value).toBe("");
    expect(container.querySelector('select[name="city_id"] option[value="city-b"]')).not.toBeNull();

    const form = container.querySelector<HTMLFormElement>("form");
    expect(form?.method).toBe("get");
    const submitted = new FormData(form!);
    expect(submitted.get("make_id")).toBe(makeB.id);
    expect(submitted.get("model_id")).toBe(modelB.id);
    expect(submitted.get("generation_id")).toBe(generationB.id);
    expect(submitted.get("region_id")).toBe(regionB.id);
    expect(submitted.get("city_id")).toBe("");
    expect(submitted.get("q")).toBe("BMW 3");
    expect(submitted.get("sort")).toBe("price_asc");
    expect(container.querySelector<HTMLSelectElement>('select[name="fuel"]')?.value).toBe("");
    await act(async () => { choose("fuel", "petrol"); });
    expect(new FormData(form!).get("fuel")).toBe("petrol");
    expect(container.querySelector('select[name="body_type"] option[value="sedan"]')?.textContent).toBe("Седан");
  });

  it("loads modifications for a changed generation and submits the selected modification", async () => {
    let resolveModifications!: (value: { items: CatalogModification[] }) => void;
    const modifications = new Promise<{ items: CatalogModification[] }>((resolve) => { resolveModifications = resolve; });
    const catalog = vi.spyOn(api, "catalog").mockImplementation(async (kind, params = {}) => {
      if (kind === "generations" && params.model_id === modelA.id) return { items: [generationA, generationNext] };
      if (kind === "modifications" && params.generation_id === generationNext.id) return modifications;
      return { items: [] };
    });

    await act(async () => {
      root.render(createElement(SearchFilters, {
        search: { make_id: makeA.id, model_id: modelA.id, generation_id: generationA.id, modification_id: modificationA.id, q: "BMW" },
        makes: [makeA],
        initialModels: [modelA],
        initialModifications: [modificationA],
        regions: [],
        initialCities: [],
        bodyTypes: []
      }));
    });

    const modificationSelect = container.querySelector<HTMLSelectElement>('select[name="modification_id"]');
    expect(modificationSelect?.value).toBe(modificationA.id);
    expect(container.querySelector(`option[value="${modificationA.id}"]`)?.textContent).toContain(modificationA.name);

    await act(async () => { choose("generation_id", generationNext.id); });
    expect(catalog).toHaveBeenCalledWith("modifications", { generation_id: generationNext.id });
    expect(modificationSelect?.value).toBe("");
    expect(modificationSelect?.disabled).toBe(true);
    expect(modificationSelect?.options[0]?.textContent).toBe("Загрузка модификаций…");

    await act(async () => {
      resolveModifications({ items: [modificationNext] });
      await Promise.resolve();
    });

    expect(modificationSelect?.disabled).toBe(false);
    expect(container.querySelector(`option[value="${modificationNext.id}"]`)?.textContent).toContain(modificationNext.name);
    await act(async () => { choose("modification_id", modificationNext.id); });
    const form = container.querySelector<HTMLFormElement>("form")!;
    expect(new FormData(form).get("modification_id")).toBe(modificationNext.id);
    expect(new FormData(form).get("q")).toBe("BMW");
  });

  it("loads body variants for the selected generation and submits the exact variant", async () => {
    const variant: CatalogItem = { id: "variant-a", slug: "sedan-a", name: "Седан", generation_id: generationA.id };
    const nextVariant: CatalogItem = { id: "variant-next", slug: "wagon-next", name: "Универсал", generation_id: generationNext.id };
    const catalog = vi.spyOn(api, "catalog").mockImplementation(async (kind, params = {}) => {
      if (kind === "body-variants" && params.generation_id === generationA.id) return { items: [variant] };
      if (kind === "body-variants" && params.generation_id === generationNext.id) return { items: [nextVariant] };
      return { items: [] };
    });

    await act(async () => {
      root.render(createElement(SearchFilters, {
        search: { q: "BMW", generation_id: "" },
        makes: [makeA],
        initialModels: [modelA],
        initialGenerations: [generationA, generationNext],
        regions: [],
        initialCities: [],
        bodyTypes: []
      }));
    });

    await act(async () => { choose("generation_id", generationA.id); await Promise.resolve(); });
    expect(catalog).toHaveBeenCalledWith("body-variants", { generation_id: generationA.id });
    expect(container.querySelector(`option[value="${variant.id}"]`)?.textContent).toBe(variant.name);

    await act(async () => { choose("body_variant_id", variant.id); });
    const form = container.querySelector<HTMLFormElement>("form")!;
    expect(form.method).toBe("get");
    expect(new FormData(form).get("body_variant_id")).toBe(variant.id);
    expect(new FormData(form).get("q")).toBe("BMW");

    await act(async () => { choose("generation_id", generationNext.id); await Promise.resolve(); });
    expect(catalog).toHaveBeenCalledWith("body-variants", { generation_id: generationNext.id });
    expect(container.querySelector<HTMLSelectElement>('select[name="body_variant_id"]')?.value).toBe("");
    expect(container.querySelector(`option[value="${nextVariant.id}"]`)?.textContent).toBe(nextVariant.name);
    expect(new FormData(form).get("body_variant_id")).toBe("");
  });

  it("ignores a delayed body-variant response after the generation changes", async () => {
    const oldVariant: CatalogItem = { id: "variant-old", slug: "sedan-old", name: "Седан прежнего поколения", generation_id: generationA.id };
    const nextVariant: CatalogItem = { id: "variant-next", slug: "wagon-next", name: "Универсал нового поколения", generation_id: generationNext.id };
    let resolveOldVariants!: (response: { items: CatalogItem[] }) => void;
    const oldVariants = new Promise<{ items: CatalogItem[] }>((resolve) => { resolveOldVariants = resolve; });
    const catalog = vi.spyOn(api, "catalog").mockImplementation(async (kind, params = {}) => {
      if (kind === "body-variants" && params.generation_id === generationA.id) return oldVariants;
      if (kind === "body-variants" && params.generation_id === generationNext.id) return { items: [nextVariant] };
      return { items: [] };
    });

    await act(async () => {
      root.render(createElement(SearchFilters, {
        search: { make_id: makeA.id, model_id: modelA.id, generation_id: generationA.id, body_variant_id: oldVariant.id },
        makes: [makeA],
        initialModels: [modelA],
        initialGenerations: [generationA, generationNext],
        regions: [],
        initialCities: [],
        bodyTypes: []
      }));
      await Promise.resolve();
    });

    expect(catalog).toHaveBeenCalledWith("body-variants", { generation_id: generationA.id });
    await act(async () => { choose("generation_id", generationNext.id); await Promise.resolve(); });
    expect(container.querySelector(`option[value="${nextVariant.id}"]`)?.textContent).toBe(nextVariant.name);

    await act(async () => {
      resolveOldVariants({ items: [oldVariant] });
      await Promise.resolve();
    });

    const bodyVariantSelect = container.querySelector<HTMLSelectElement>('select[name="body_variant_id"]');
    expect(bodyVariantSelect?.value).toBe("");
    expect(container.querySelector(`option[value="${nextVariant.id}"]`)?.textContent).toBe(nextVariant.name);
    expect(container.querySelector(`option[value="${oldVariant.id}"]`)).toBeNull();
    expect(new FormData(container.querySelector<HTMLFormElement>("form")!).get("body_variant_id")).toBe("");
  });

  it("restores and clears the selected body variant when URL search state changes", async () => {
    const variant: CatalogItem = { id: "variant-a", slug: "sedan-a", name: "Седан", generation_id: generationA.id };
    vi.spyOn(api, "catalog").mockImplementation(async (kind) => kind === "body-variants" ? { items: [variant] } : { items: [] });
    const props = {
      makes: [makeA],
      initialModels: [modelA],
      initialGenerations: [generationA],
      regions: [],
      initialCities: [],
      bodyTypes: []
    };

    await act(async () => {
      root.render(createElement(SearchFilters, {
        ...props,
        search: { model_id: modelA.id, generation_id: generationA.id, body_variant_id: variant.id }
      }));
      await Promise.resolve();
    });

    expect(container.querySelector<HTMLSelectElement>('select[name="body_variant_id"]')?.value).toBe(variant.id);
    expect(new FormData(container.querySelector<HTMLFormElement>("form")!).get("body_variant_id")).toBe(variant.id);

    await act(async () => {
      root.render(createElement(SearchFilters, {
        ...props,
        search: { model_id: modelA.id, generation_id: generationA.id }
      }));
    });

    expect(container.querySelector<HTMLSelectElement>('select[name="body_variant_id"]')?.value).toBe("");
    expect(new FormData(container.querySelector<HTMLFormElement>("form")!).get("body_variant_id")).toBe("");
  });

  it("announces modification catalog errors and empty results", async () => {
    const catalog = vi.spyOn(api, "catalog").mockImplementation(async (kind) => {
      if (kind === "generations") return { items: [generationA, generationNext] };
      if (kind === "modifications") throw new Error("catalog unavailable");
      return { items: [] };
    });

    await act(async () => {
      root.render(createElement(SearchFilters, {
        search: { make_id: makeA.id, model_id: modelA.id, generation_id: generationA.id, modification_id: modificationA.id },
        makes: [makeA],
        initialModels: [modelA],
        initialModifications: [modificationA],
        regions: [],
        initialCities: [],
        bodyTypes: []
      }));
    });

    await act(async () => { choose("generation_id", generationNext.id); await Promise.resolve(); });
    expect(container.querySelector('[role="status"]')?.textContent).toContain("Не удалось загрузить модификации");
    expect(container.querySelector<HTMLSelectElement>('select[name="modification_id"]')?.value).toBe("");

    catalog.mockImplementation(async (kind) => kind === "generations" ? { items: [generationA, generationNext] } : { items: [] });
    await act(async () => { choose("generation_id", generationA.id); await Promise.resolve(); });
    const modificationSelect = container.querySelector<HTMLSelectElement>('select[name="modification_id"]');
    expect(modificationSelect?.disabled).toBe(true);
    expect(modificationSelect?.options[0]?.textContent).toBe("Нет доступных модификаций");
  });
});
