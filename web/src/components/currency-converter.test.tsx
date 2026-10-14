import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CurrencyConverter } from "@/components/currency-converter";
import type { components } from "@/lib/types.generated";

type CurrencyRates = components["schemas"]["CustomsRatesResponse"];
type RateHistory = components["schemas"]["CustomsRateHistoryResponse"];

const rates: CurrencyRates = {
  rate_date: "2026-10-04",
  rates: [
    { currency: "BYN", official_rate: "1", scale: 1, byn_per_unit: "1" },
    { currency: "EUR", official_rate: "3.5", scale: 1, byn_per_unit: "3.5" },
    { currency: "USD", official_rate: "3.21", scale: 1, byn_per_unit: "3.21" },
    { currency: "RUB", official_rate: "3.6", scale: 100, byn_per_unit: "0.036" },
    { currency: "CNY", official_rate: "4.5", scale: 10, byn_per_unit: "0.45" }
  ]
};

function history(period: RateHistory["period"] = "90d"): RateHistory {
  return {
    currency: "USD",
    period,
    rate_date: "2026-10-04",
    start_date: period === "30d" ? "2026-09-05" : "2026-07-07",
    end_date: "2026-10-04",
    source_url: "https://api.nbrb.by/exrates/rates/dynamics/431?startdate=2026-07-07&enddate=2026-10-04",
    points: [
      { rate_date: "2026-10-03", official_rate: "3.2", scale: 1, byn_per_unit: "3.2" },
      { rate_date: "2026-10-04", official_rate: "3.21", scale: 1, byn_per_unit: "3.21" }
    ]
  };
}

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

function setValue(element: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(element), "value")?.set;
  setter?.call(element, value);
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
}

describe("CurrencyConverter", () => {
  it("shows the official date and synchronizes all four currency amounts", async () => {
    await act(async () => root.render(createElement(CurrencyConverter, { rates, initialHistory: history() })));

    expect(container.textContent).toContain("НБРБ на 4 октября 2026 г.");
    expect(container.querySelectorAll("input[name]")).toHaveLength(4);
    expect(container.querySelector<HTMLInputElement>('input[name="USD"]')?.value).toBe("1");
    expect(container.querySelector<HTMLInputElement>('input[name="BYN"]')?.value).toBe("3,21");
    expect(container.querySelector<HTMLInputElement>('input[name="RUB"]')?.value).toBe("89,17");
    expect(container.querySelector<HTMLInputElement>('input[name="EUR"]')?.value).toBe("0,92");

    const rub = container.querySelector<HTMLInputElement>('input[name="RUB"]')!;
    await act(async () => {
      rub.focus();
      setValue(rub, "100");
    });
    expect(container.querySelector<HTMLInputElement>('input[name="USD"]')?.value).toBe("1,12");
    expect(container.querySelector<HTMLInputElement>('input[name="BYN"]')?.value).toBe("3,60");
  });

  it("shows a validation message for malformed input", async () => {
    await act(async () => root.render(createElement(CurrencyConverter, { rates, initialHistory: history() })));
    const amount = container.querySelector<HTMLInputElement>('input[name="USD"]')!;

    await act(async () => setValue(amount, "1,2,3"));

    expect(container.querySelector('[role="alert"]')?.textContent).toBe("Введите сумму числом, используя запятую или точку.");
    expect(container.querySelector<HTMLInputElement>('input[name="BYN"]')?.value).toBe("");
  });

  it("requests the selected NBRB history period", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(history("30d")), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    }));
    vi.stubGlobal("fetch", fetch);
    await act(async () => root.render(createElement(CurrencyConverter, { rates, initialHistory: history() })));

    const monthButton = Array.from(container.querySelectorAll("button")).find((button) => button.textContent === "1 месяц")!;
    await act(async () => {
      monthButton.click();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/customs-calculator/rates/history?currency=USD&period=30d",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(monthButton.getAttribute("aria-pressed")).toBe("true");
  });

  it("plots the selected amount using each historical rate scale", async () => {
    const rubHistory: RateHistory = {
      ...history(),
      currency: "RUB",
      points: [
        { rate_date: "2026-09-01", official_rate: "3.6", scale: 100, byn_per_unit: "0.036" },
        { rate_date: "2026-10-04", official_rate: "0.036", scale: 1, byn_per_unit: "0.036" }
      ]
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(rubHistory), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    })));

    await act(async () => root.render(createElement(CurrencyConverter, { rates, initialHistory: history() })));
    const rubButton = Array.from(container.querySelectorAll("button")).find((button) => button.textContent === "100 RUB")!;
    await act(async () => {
      rubButton.click();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    const markerTitles = Array.from(container.querySelectorAll("circle title"), (title) => title.textContent);
    expect(markerTitles).toEqual([
      "1 сентября 2026 г.: 3,6 BYN",
      "4 октября 2026 г.: 3,6 BYN"
    ]);
    expect(container.textContent).toContain("0 BYN (0,00%) за период");
  });
});
