import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CurrencyConverter } from "@/components/currency-converter";
import type { components } from "@/lib/types.generated";

const rates: components["schemas"]["CustomsRatesResponse"] = {
  rate_date: "2026-10-04",
  rates: [
    { currency: "BYN", official_rate: "1", scale: 1, byn_per_unit: "1" },
    { currency: "EUR", official_rate: "3.5", scale: 1, byn_per_unit: "3.5" },
    { currency: "USD", official_rate: "3.21", scale: 1, byn_per_unit: "3.21" },
    { currency: "RUB", official_rate: "3.5", scale: 100, byn_per_unit: "0.035" },
    { currency: "CNY", official_rate: "4.5", scale: 10, byn_per_unit: "0.45" }
  ]
};

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
  vi.unstubAllGlobals();
});

function setValue(element: HTMLInputElement | HTMLSelectElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(element), "value")?.set;
  setter?.call(element, value);
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
}

describe("CurrencyConverter", () => {
  it("converts locally and swaps currencies without making a request", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    await act(async () => root.render(createElement(CurrencyConverter, { rates })));

    const amount = container.querySelector<HTMLInputElement>('input[name="amount"]')!;
    await act(async () => setValue(amount, "100"));
    expect(container.querySelector("output")?.textContent).toBe("31,15 USD");
    expect(container.textContent).toContain("Официальный курс НБРБ на 2026-10-04");

    await act(async () => container.querySelector<HTMLButtonElement>(".currency-converter-swap")?.click());

    expect(container.querySelector("output")?.textContent).toBe("321,00 BYN");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("shows a validation message when the amount is malformed", async () => {
    await act(async () => root.render(createElement(CurrencyConverter, { rates })));
    const amount = container.querySelector<HTMLInputElement>('input[name="amount"]')!;

    await act(async () => setValue(amount, "1,2,3"));

    expect(container.querySelector('[role="alert"]')?.textContent).toBe("Проверьте сумму и выбранные валюты.");
    expect(container.querySelector("output")).toBeNull();
  });
});
