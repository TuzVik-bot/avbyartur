import { describe, expect, it } from "vitest";
import { formatDate, formatMileage, formatMoney, listingPhotoAlt } from "@/lib/format";
import type { Money } from "@/lib/types";

describe("automatic listing photo alt", () => {
  it("uses the current listing heading and an optional photo number", () => {
    expect(listingPhotoAlt(" BMW 530d 2020 ")).toBe("Продажа авто — BMW 530d 2020");
    expect(listingPhotoAlt("BMW 530d 2020", 2)).toBe("Продажа авто — BMW 530d 2020 — фото 2");
    expect(listingPhotoAlt(" ")).toBe("Продажа авто — объявление");
  });
});

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

describe("user-facing dates", () => {
  it("renders the Minsk calendar day regardless of the server time zone", () => {
    // 22:30 UTC on 31 December is already 1 January in Minsk (UTC+3).
    expect(formatDate("2026-12-31T22:30:00Z")).toBe(new Intl.DateTimeFormat("ru-BY", { dateStyle: "medium", timeZone: "Europe/Minsk" }).format(new Date("2027-01-01T12:00:00Z")));
  });

  it("keeps an unparsable value as is", () => {
    expect(formatDate("не дата")).toBe("не дата");
  });
});
