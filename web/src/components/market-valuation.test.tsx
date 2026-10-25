import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MarketValuation } from "@/components/market-valuation";
import { api } from "@/lib/api";
import type { CatalogItem } from "@/lib/types";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      catalog: vi.fn(),
      marketValuation: vi.fn(),
    },
  };
});

const catalog = vi.mocked(api.catalog);
const marketValuation = vi.mocked(api.marketValuation);

const makes: CatalogItem[] = [{ id: "make-1", slug: "bmw", name: "BMW" }];
const models: CatalogItem[] = [{ id: "model-1", slug: "3-series", name: "3 Series", make_id: "make-1" }];
const bodyTypes: CatalogItem[] = [{ id: "body-1", slug: "sedan", name: "Седан" }];

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  catalog.mockReset();
  marketValuation.mockReset();
  catalog.mockImplementation((kind: string) => {
    if (kind === "models") return Promise.resolve({ items: models });
    if (kind === "generations") return Promise.resolve({ items: [] });
    return Promise.resolve({ items: [] });
  });
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

function setSelect(label: string, value: string) {
  const select = [...container.querySelectorAll("select")].find((element) =>
    element.closest("label")?.textContent?.includes(label),
  )!;
  const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")?.set;
  setter?.call(select, value);
  select.dispatchEvent(new Event("change", { bubbles: true }));
}

function setInput(label: string, value: string) {
  const input = [...container.querySelectorAll("input")].find((element) =>
    element.closest("label")?.textContent?.includes(label),
  )!;
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
  setter?.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

describe("market valuation page component", () => {
  it("keeps the submit disabled until the form is complete", async () => {
    await act(async () => {
      root.render(createElement(MarketValuation, { makes, bodyTypes, catalogUnavailable: false }));
    });
    const button = container.querySelector<HTMLButtonElement>("button[type=submit]")!;
    expect(button.disabled).toBe(true);
    setSelect("Марка", "make-1");
    await act(async () => { await Promise.resolve(); });
    setSelect("Модель", "model-1");
    setSelect("Тип кузова", "body-1");
    setInput("Год выпуска", "2016");
    setInput("Пробег, км", "150000");
    const enabled = container.querySelector<HTMLButtonElement>("button[type=submit]")!;
    expect(enabled.disabled).toBe(false);
  });

  it("renders a high-confidence range with a submit call to action", async () => {
    marketValuation.mockResolvedValue({
      status: "high",
      median_byn: "10000.00",
      p25_byn: "9000.00",
      p75_byn: "12000.00",
      sample_size: 12,
      seller_count: 6,
      as_of: "2026-10-25",
      rate_date: null,
    });
    await act(async () => {
      root.render(createElement(MarketValuation, { makes, bodyTypes, catalogUnavailable: false }));
    });
    setSelect("Марка", "make-1");
    await act(async () => { await Promise.resolve(); });
    setSelect("Модель", "model-1");
    setSelect("Тип кузова", "body-1");
    setInput("Год выпуска", "2016");
    setInput("Пробег, км", "150000");
    await act(async () => { container.querySelector<HTMLButtonElement>("button[type=submit]")!.click(); });
    expect(marketValuation).toHaveBeenCalledWith(expect.objectContaining({ make_id: "make-1", model_id: "model-1", body_type_id: "body-1", year: 2016, mileage_km: 150000 }));
    expect(container.querySelector("[data-valuation-result]")!.textContent).toContain("Надёжная оценка");
    expect(container.querySelector("[data-valuation-result]")!.textContent).toContain("Подать объявление");
  });

  it("explains an empty market instead of inventing numbers", async () => {
    marketValuation.mockResolvedValue({
      status: "none",
      median_byn: null,
      p25_byn: null,
      p75_byn: null,
      sample_size: 1,
      seller_count: 1,
      as_of: "2026-10-25",
      rate_date: null,
    });
    await act(async () => {
      root.render(createElement(MarketValuation, { makes, bodyTypes, catalogUnavailable: false }));
    });
    setSelect("Марка", "make-1");
    await act(async () => { await Promise.resolve(); });
    setSelect("Модель", "model-1");
    setSelect("Тип кузова", "body-1");
    setInput("Год выпуска", "2016");
    setInput("Пробег, км", "150000");
    await act(async () => { container.querySelector<HTMLButtonElement>("button[type=submit]")!.click(); });
    expect(container.querySelector("[data-valuation-result]")!.textContent).toContain("мало похожих объявлений");
  });
});
