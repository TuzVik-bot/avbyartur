import { describe, expect, it } from "vitest";
import { convertCurrencyAmount, formatMileage, formatMoney } from "@/lib/format";
import type { Money } from "@/lib/types";

function formatted(amount: string, currency: Money["currency"]) {
  return `${new Intl.NumberFormat("ru-BY", { maximumFractionDigits: 0 }).format(Number(amount))} ${currency}`;
}

describe("formatMoney", () => {
  it("renders an explicit fallback when a draft has no price", () => {
    expect(formatMoney(null)).toBe("Цена не указана");
  });

  it("uses the requested BYN display pair while preserving the source USD price", () => {
    const price: Money = {
      amount: "10000",
      currency: "USD",
      display_amount: "32000",
      display_currency: "BYN",
      display_byn: "31000",
      rate_date: "2026-09-26"
    };

    expect(formatMoney(price)).toBe(formatted("32000", "BYN"));
  });

  it("uses the requested USD display pair for a source BYN price", () => {
    const price: Money = {
      amount: "32000",
      currency: "BYN",
      display_amount: "10000",
      display_currency: "USD"
    };

    expect(formatMoney(price)).toBe(formatted("10000", "USD"));
  });

  it("falls back to the raw currency when the display pair is incomplete or stale", () => {
    const price: Money = {
      amount: "25000",
      currency: "BYN",
      display_amount: "20000",
      display_currency: null,
      rate_date: "2020-01-01"
    };

    expect(formatMoney(price)).toBe(formatted("25000", "BYN"));
  });

  it("keeps the legacy USD-to-BYN display fallback", () => {
    const price: Money = {
      amount: "10000",
      currency: "USD",
      display_byn: "31500",
      rate_date: "2026-09-26"
    };

    expect(formatMoney(price)).toBe(formatted("31500", "BYN"));
  });
});

describe("formatMileage", () => {
  it("renders an explicit fallback when a draft has no mileage", () => {
    expect(formatMileage(null)).toBe("Пробег не указан");
  });
});

describe("convertCurrencyAmount", () => {
  it("converts between currencies with exact official-rate rounding", () => {
    expect(convertCurrencyAmount("100", "EUR", "USD", [
      { currency: "EUR", byn_per_unit: "3.5" },
      { currency: "USD", byn_per_unit: "3.21" },
      { currency: "BYN", byn_per_unit: "1" }
    ])).toBe("109.03");
  });

  it("rejects malformed amounts and currencies without a rate", () => {
    const rates = [{ currency: "BYN", byn_per_unit: "1" }];

    expect(convertCurrencyAmount("-4", "BYN", "BYN", rates)).toBeNull();
    expect(convertCurrencyAmount("10", "USD", "BYN", rates)).toBeNull();
  });

  it("accepts a decimal comma and caps amounts at the documented maximum", () => {
    const rates = [
      { currency: "BYN", byn_per_unit: "1" },
      { currency: "USD", byn_per_unit: "3.5" }
    ];

    expect(convertCurrencyAmount("3,50", "USD", "BYN", rates)).toBe("12.25");
    expect(convertCurrencyAmount("1000000000000000001", "BYN", "USD", rates)).toBeNull();
  });
});
