import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HomeSearch } from "@/components/home-search";
import { api } from "@/lib/api";
import type { CatalogItem } from "@/lib/types";

const make: CatalogItem = { id: "make-1", slug: "make", name: "Марка" };
const model: CatalogItem = { id: "model-1", slug: "model", name: "Модель", make_id: make.id };
const region: CatalogItem = { id: "region-1", slug: "region", name: "Минская область" };

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  vi.useFakeTimers();
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function change(name: string, value: string) {
  const field = container.querySelector<HTMLInputElement | HTMLSelectElement>(`[name="${name}"]`);
  if (!field) throw new Error(`Missing field ${name}`);
  act(() => {
    field.value = value;
    field.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

describe("home search", () => {
  it("submits the quick filters and counts matching listings after a 300ms debounce", async () => {
    const count = vi.spyOn(api, "listingCount").mockResolvedValue({ total: 42 });
    vi.spyOn(api, "catalog").mockResolvedValue({ items: [model] });
    await act(async () => root.render(createElement(HomeSearch, { makes: [make], regions: [region], bodyTypes: [{ id: "sedan-id", slug: "sedan", name: "Седан" }] })));

    change("q", "BMW");
    change("make_id", make.id);
    await act(async () => { await Promise.resolve(); });
    change("model_id", model.id);
    change("price_min", "10000");
    change("price_max", "20000");
    change("year_min", "2018");
    change("year_max", "2022");
    change("mileage_min", "10000");
    change("mileage_max", "80000");
    change("transmission", "automatic");
    change("fuel", "petrol");
    change("body_type", "sedan");
    change("region_id", region.id);

    await act(async () => { vi.advanceTimersByTime(299); });
    expect(count).not.toHaveBeenCalled();
    await act(async () => { vi.advanceTimersByTime(1); await Promise.resolve(); });

    expect(count).toHaveBeenLastCalledWith(expect.objectContaining({
      q: "BMW", make_id: make.id, model_id: model.id, price_min: "10000", price_max: "20000", currency: "BYN",
      year_min: "2018", year_max: "2022", mileage_min: "10000", mileage_max: "80000",
      transmission: "automatic", fuel: "petrol", body_type: "sedan", region_id: region.id
    }));
    expect(container.textContent).toContain("42");
    expect(container.querySelector(".home-search-button")?.textContent).toContain("Показать 42 предложения");
    const form = container.querySelector<HTMLFormElement>("form")!;
    expect(form.action).toContain("/cars");
    expect(new FormData(form).get("model_id")).toBe(model.id);
    expect(new FormData(form).get("region_id")).toBe(region.id);
    expect(new FormData(form).get("currency")).toBe("BYN");
  });

  it("ignores older count responses and returns to generic text after an error", async () => {
    let resolveFirst!: (value: { total: number }) => void;
    let resolveSecond!: (value: { total: number }) => void;
    const count = vi.spyOn(api, "listingCount")
      .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve; }))
      .mockImplementationOnce(() => new Promise((resolve) => { resolveSecond = resolve; }))
      .mockRejectedValueOnce(new Error("offline"));
    await act(async () => root.render(createElement(HomeSearch, { makes: [], regions: [], bodyTypes: [] })));

    change("q", "BMW");
    await act(async () => { vi.advanceTimersByTime(300); });
    change("q", "Audi");
    await act(async () => { vi.advanceTimersByTime(300); });
    await act(async () => { resolveSecond({ total: 8 }); });
    await act(async () => { resolveFirst({ total: 99 }); });
    expect(container.textContent).toContain("8");
    expect(container.textContent).not.toContain("99");

    change("q", "Volvo");
    await act(async () => { vi.advanceTimersByTime(300); await Promise.resolve(); });
    expect(container.querySelector('[data-count-state="generic"]')).not.toBeNull();
    expect(count).toHaveBeenCalledTimes(3);
  });

  it("loads models only for the selected make and clears the dependent model", async () => {
    const catalog = vi.spyOn(api, "catalog").mockResolvedValue({ items: [model] });
    await act(async () => root.render(createElement(HomeSearch, { makes: [make], regions: [], bodyTypes: [] })));

    change("make_id", make.id);
    await act(async () => { await Promise.resolve(); });
    expect(catalog).toHaveBeenCalledWith("models", { make_id: make.id });
    expect(container.querySelector<HTMLSelectElement>('select[name="model_id"]')?.disabled).toBe(false);
  });

  it("ignores a model catalog response after the user selects another make", async () => {
    const makeB: CatalogItem = { id: "make-2", slug: "make-2", name: "Другая марка" };
    const modelB: CatalogItem = { id: "model-2", slug: "model-2", name: "Другая модель", make_id: makeB.id };
    let resolveA!: (value: { items: CatalogItem[] }) => void;
    let resolveB!: (value: { items: CatalogItem[] }) => void;
    const catalog = vi.spyOn(api, "catalog").mockImplementation((_kind, params = {}) => new Promise((resolve) => {
      if (params.make_id === make.id) resolveA = resolve;
      else resolveB = resolve;
    }));
    await act(async () => root.render(createElement(HomeSearch, { makes: [make, makeB], regions: [], bodyTypes: [] })));
    change("make_id", make.id);
    await act(async () => { await Promise.resolve(); });
    change("make_id", makeB.id);
    await act(async () => { await Promise.resolve(); });

    await act(async () => { resolveA({ items: [model] }); });
    expect(container.querySelector<HTMLSelectElement>('select[name="model_id"]')?.disabled).toBe(true);
    await act(async () => { resolveB({ items: [modelB] }); });
    expect(catalog).toHaveBeenCalledTimes(2);
    expect(container.querySelector(`option[value="${model.id}"]`)).toBeNull();
    expect(container.querySelector(`option[value="${modelB.id}"]`)?.textContent).toBe(modelB.name);
  });

  it("uses Russian plural forms for zero and one result", async () => {
    const count = vi.spyOn(api, "listingCount").mockResolvedValueOnce({ total: 1 }).mockResolvedValueOnce({ total: 0 });
    await act(async () => root.render(createElement(HomeSearch, { makes: [], regions: [], bodyTypes: [] })));
    change("q", "Volvo");
    await act(async () => { vi.advanceTimersByTime(300); await Promise.resolve(); });
    expect(container.querySelector(".home-search-button")?.textContent).toContain("Показать 1 предложение");
    change("q", "Fiat");
    await act(async () => { vi.advanceTimersByTime(300); await Promise.resolve(); });
    expect(container.querySelector(".home-search-button")?.textContent).toContain("Показать 0 предложений");
    expect(count).toHaveBeenCalledTimes(2);
  });
});
