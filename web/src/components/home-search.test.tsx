import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HomeSearch } from "@/components/home-search";
import { api } from "@/lib/api";
import type { CatalogItem } from "@/lib/types";

const makeA: CatalogItem = { id: "make-a", slug: "make-a", name: "Марка A" };
const makeB: CatalogItem = { id: "make-b", slug: "make-b", name: "Марка B" };
const modelA: CatalogItem = { id: "model-a", slug: "model-a", name: "Модель A", make_id: makeA.id };
const modelB: CatalogItem = { id: "model-b", slug: "model-b", name: "Модель B", make_id: makeB.id };

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

function chooseMake(id: string) {
  const select = container.querySelector<HTMLSelectElement>('select[name="make_id"]')!;
  select.value = id;
  select.dispatchEvent(new Event("change", { bubbles: true }));
}

describe("home search", () => {
  it("loads models for the selected make and submits make, model, and maximum price", async () => {
    const catalog = vi.spyOn(api, "catalog").mockImplementation(async (kind, params = {}) =>
      kind === "models" && params.make_id === makeA.id ? { items: [modelA] } : { items: [] }
    );

    await act(async () => root.render(createElement(HomeSearch, { makes: [makeA], priceOperationsAvailable: true })));
    await act(async () => { chooseMake(makeA.id); await Promise.resolve(); });

    expect(catalog).toHaveBeenCalledWith("models", { make_id: makeA.id });
    const modelSelect = container.querySelector<HTMLSelectElement>('select[name="model_id"]')!;
    expect(modelSelect.disabled).toBe(false);
    expect(container.querySelector(`option[value="${modelA.id}"]`)?.textContent).toBe(modelA.name);
    await act(async () => {
      modelSelect.value = modelA.id;
      modelSelect.dispatchEvent(new Event("change", { bubbles: true }));
    });
    const priceInput = container.querySelector<HTMLInputElement>('input[name="price_max"]')!;
    priceInput.value = "25000";

    const form = container.querySelector<HTMLFormElement>("form")!;
    const submitted = new FormData(form);
    expect(form.method).toBe("get");
    expect(form.getAttribute("action")).toBe("/cars");
    expect(submitted.get("make_id")).toBe(makeA.id);
    expect(submitted.get("model_id")).toBe(modelA.id);
    expect(submitted.get("price_max")).toBe("25000");
  });

  it("does not submit the previous model when the make changes immediately before submit", async () => {
    vi.spyOn(api, "catalog").mockImplementation((_kind, params = {}) =>
      params.make_id === makeA.id ? Promise.resolve({ items: [modelA] }) : new Promise(() => {})
    );

    await act(async () => root.render(createElement(HomeSearch, { makes: [makeA, makeB], priceOperationsAvailable: true })));
    await act(async () => { chooseMake(makeA.id); await Promise.resolve(); });

    const modelSelect = container.querySelector<HTMLSelectElement>('select[name="model_id"]')!;
    await act(async () => {
      modelSelect.value = modelA.id;
      modelSelect.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(modelSelect.value).toBe(modelA.id);

    const form = container.querySelector<HTMLFormElement>("form")!;
    let submitted: FormData | undefined;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      submitted = new FormData(form);
    }, { once: true });

    await act(() => {
      chooseMake(makeB.id);
      form.requestSubmit();
    });

    expect(submitted?.get("make_id")).toBe(makeB.id);
    expect(submitted?.get("model_id")).not.toBe(modelA.id);
  });

  it("ignores an older model response after the make changes", async () => {
    let resolveMakeA!: (value: { items: CatalogItem[] }) => void;
    let resolveMakeB!: (value: { items: CatalogItem[] }) => void;
    const makeAModels = new Promise<{ items: CatalogItem[] }>((resolve) => { resolveMakeA = resolve; });
    const makeBModels = new Promise<{ items: CatalogItem[] }>((resolve) => { resolveMakeB = resolve; });
    vi.spyOn(api, "catalog").mockImplementation((kind, params = {}) => {
      if (kind === "models" && params.make_id === makeA.id) return makeAModels;
      if (kind === "models" && params.make_id === makeB.id) return makeBModels;
      return Promise.resolve({ items: [] });
    });

    await act(async () => root.render(createElement(HomeSearch, { makes: [makeA, makeB], priceOperationsAvailable: true })));
    await act(async () => { chooseMake(makeA.id); });
    await act(async () => { chooseMake(makeB.id); });
    await act(async () => { resolveMakeB({ items: [modelB] }); await Promise.resolve(); });
    await act(async () => { resolveMakeA({ items: [modelA] }); await Promise.resolve(); });

    expect(container.querySelector(`option[value="${modelB.id}"]`)?.textContent).toBe(modelB.name);
    expect(container.querySelector(`option[value="${modelA.id}"]`)).toBeNull();
  });

  it("does not submit a price filter when the exchange rate is unavailable", async () => {
    await act(async () => root.render(createElement(HomeSearch, { makes: [makeA], priceOperationsAvailable: false })));

    const priceInput = container.querySelector<HTMLInputElement>('input[name="price_max"]')!;
    expect(priceInput.disabled).toBe(true);
    expect(priceInput.getAttribute("aria-describedby")).toBe("home-price-status");
    expect(container.querySelector("#home-price-status")?.textContent).toContain("нет подтверждённого курса НБРБ за последние 72 часа");

    priceInput.value = "25000";
    expect(new FormData(container.querySelector("form")!).has("price_max")).toBe(false);
  });

  it("shows a model catalog error and retries the selected make", async () => {
    const catalog = vi.spyOn(api, "catalog")
      .mockRejectedValueOnce(new Error("catalog unavailable"))
      .mockResolvedValueOnce({ items: [modelA] });

    await act(async () => root.render(createElement(HomeSearch, { makes: [makeA], priceOperationsAvailable: true })));
    await act(async () => { chooseMake(makeA.id); await Promise.resolve(); });

    expect(container.querySelector('[role="status"]')?.textContent).toContain("Не удалось загрузить модели");
    const retryButton = container.querySelector<HTMLButtonElement>(".home-model-error button")!;
    await act(async () => { retryButton.click(); await Promise.resolve(); });

    expect(catalog).toHaveBeenNthCalledWith(1, "models", { make_id: makeA.id });
    expect(catalog).toHaveBeenNthCalledWith(2, "models", { make_id: makeA.id });
    expect(container.querySelector('[role="status"]')).toBeNull();
    expect(container.querySelector(`option[value="${modelA.id}"]`)?.textContent).toBe(modelA.name);
    expect(container.querySelector<HTMLSelectElement>('select[name="model_id"]')?.disabled).toBe(false);
  });
});
