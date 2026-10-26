import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import { OwnershipCalculator } from "@/components/ownership-calculator";
import type { OwnershipVehicleSeed } from "@/components/ownership-calculator";
import type { Listing } from "@/lib/types";

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

function render() {
  act(() => root.render(createElement(OwnershipCalculator)));
}

function setValue(selector: string, value: string) {
  const element = container.querySelector<HTMLInputElement | HTMLSelectElement>(selector)!;
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(element), "value")?.set;
  act(() => {
    setter?.call(element, value);
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

describe("ownership calculator", () => {
  it("shows an example estimate with monthly, total, and per kilometre costs", () => {
    render();

    expect(container.querySelector<HTMLInputElement>('[aria-label="Название автомобиля 1"]')?.value).toBe("Пример расчёта");
    expect(container.textContent).toContain("Бюджет в месяц");
    expect(container.textContent).toContain("За весь срок");
    expect(container.textContent).toContain("Стоимость километра");
    expect(container.textContent).toContain("BYN");
  });

  it("recalculates when a decimal value is entered with a comma", () => {
    render();
    const before = container.querySelector('[data-result="total"]')?.textContent;

    setValue('[name="vehicle-0-priceByn"]', "36000,50");

    expect(container.querySelector('[data-result="total"]')?.textContent).not.toBe(before);
  });

  it("suppresses totals and explains an empty price instead of treating it as zero", () => {
    render();

    setValue('[name="vehicle-0-priceByn"]', "");

    expect(container.querySelector('[data-result="monthly"]')).toBeNull();
    expect(container.textContent).toContain("Введите цену автомобиля");
  });

  it("compares two vehicles under shared usage assumptions", () => {
    render();
    act(() => container.querySelector<HTMLButtonElement>("[data-action='add-vehicle']")!.click());

    expect(container.querySelector('[name="vehicle-1-priceByn"]')).not.toBeNull();
    expect(container.querySelectorAll('[name="shared-years"]')).toHaveLength(1);
    expect(container.querySelectorAll('[name="shared-annualKm"]')).toHaveLength(1);
    expect(container.textContent).toContain("Сравнение автомобилей");
    expect(container.querySelector('[data-comparison-delta]')).toBeNull();
  });

  it("shows the cheaper total cost under the same shared usage assumptions", () => {
    render();
    act(() => container.querySelector<HTMLButtonElement>("[data-action='add-vehicle']")!.click());
    setValue('[name="vehicle-1-priceByn"]', "26000");

    expect(container.querySelector('[data-comparison-delta]')?.textContent).toContain("дешевле за выбранный срок");
  });

  it("switches fuel inputs for electric energy and shows loan payment details", () => {
    render();

    setValue('[name="vehicle-0-energyType"]', "electric");
    expect(container.querySelector('[name="vehicle-0-fuelLitresPer100Km"]')).toBeNull();
    expect(container.querySelector('[name="vehicle-0-electricityKwhPer100Km"]')).not.toBeNull();

    setValue('[name="vehicle-0-loanAmountByn"]', "15000");
    expect(container.textContent).toContain("полный платёж по кредиту");
    expect(container.textContent).toContain("после погашения кредита");
  });

  it("blocks a loan amount above the vehicle price", () => {
    render();

    setValue('[name="vehicle-0-loanAmountByn"]', "35000");

    expect(container.querySelector('[data-result="total"]')).toBeNull();
    expect(container.textContent).toContain("Сумма кредита не может превышать цену автомобиля.");
  });

  it("does not invent a price when a listing seed has no published price", () => {
    const seed: OwnershipVehicleSeed = { id: "listing-1", title: "Автомобиль из объявления", input: {}, provenance: ["Цена в объявлении не указана"] };
    act(() => root.render(createElement(OwnershipCalculator, { initialVehicles: [seed], notices: ["Данные объявления — ориентир"] })));

    expect(container.querySelector('[data-result="total"]')).toBeNull();
    expect(container.textContent).toContain("Введите цену автомобиля.");
    expect(container.textContent).toContain("Данные объявления — ориентир");
  });

  it("requires energy usage values that are absent from a public listing", () => {
    const seed: OwnershipVehicleSeed = {
      id: "listing-1", title: "Объявление", input: { priceByn: 24000, resaleByn: 14000, energyType: "fuel" },
      provenance: ["Расход топлива не указан"], missingFields: ["fuelLitresPer100Km", "fuelPriceByn"]
    };
    act(() => root.render(createElement(OwnershipCalculator, { initialVehicles: [seed] })));

    expect(container.querySelector('[data-result="total"]')).toBeNull();
    expect(container.textContent).toContain("Введите значение: расход топлива, л / 100 км.");
    expect(container.textContent).toContain("Введите значение: цена топлива за литр.");
  });

  it("preserves manual estimates and shared conditions while loading a public comparison listing", async () => {
    const listingId = "123e4567-e89b-42d3-a456-426614174000";
    const listing = {
      id: listingId, title: "Машина из объявления", slug: "listing", make: { slug: "a" }, model: { slug: "b" }, fuel: "petrol",
      price: { amount: "24500", currency: "BYN", display_byn: "24500", rate_date: "2026-10-26" }
    } as unknown as Listing;
    vi.spyOn(api, "listing").mockResolvedValue({ listing });
    render();
    setValue('[name="vehicle-0-priceByn"]', "34000");
    setValue('[name="shared-years"]', "5");
    setValue("#compare-listing", `${window.location.origin}/cars/a/b/${listingId}`);

    await act(async () => {
      container.querySelector<HTMLFormElement>("form")!.requestSubmit();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(api.listing).toHaveBeenCalledWith(listingId);
    expect(container.querySelector<HTMLInputElement>('[name="vehicle-0-priceByn"]')?.value).toBe("34000");
    expect(container.querySelector<HTMLInputElement>('[name="vehicle-1-priceByn"]')?.value).toBe("24500");
    expect(container.querySelector<HTMLInputElement>('[name="shared-years"]')?.value).toBe("5");
  });

  it("keeps missing insurance, tax, and inspection visible as excluded estimates", () => {
    render();

    expect(container.textContent).toContain("Страховка");
    expect(container.textContent).toContain("Налог");
    expect(container.textContent).toContain("Техосмотр");
    expect(container.textContent).toContain("страховка: не включено — уточните сумму");
    expect(container.textContent).toContain("На старте");
  });

  it("removes excluded cost notices once all three amounts are entered", () => {
    render();
    setValue('[name="vehicle-0-annualInsuranceByn"]', "800");
    setValue('[name="vehicle-0-annualTaxByn"]', "120");
    setValue('[name="vehicle-0-annualInspectionByn"]', "80");

    expect(container.textContent).not.toContain("Что пока не включено");
  });
});
