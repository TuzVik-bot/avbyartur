import { describe, expect, it } from "vitest";
import { buildComparisonRows } from "@/components/comparison/comparison-data";
import type { Listing } from "@/lib/types";

function listing(overrides: Partial<Listing> = {}): Listing {
  return {
    id: "one",
    slug: "one",
    title: "Марка Модель",
    make: { id: "make-1", slug: "marka", name: "Марка" },
    model: { id: "model-1", slug: "model", name: "Модель" },
    year: 2020,
    mileage_km: 50000,
    fuel: "petrol",
    transmission: "manual",
    drive: "front",
    price: { amount: "10000", currency: "BYN" },
    region: { id: "region-1", slug: "region", name: "Область" },
    city: { id: "city-1", slug: "minsk", name: "Минск" },
    seller: { id: "seller-1", type: "private", name: "Продавец" },
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
    damaged: false,
    parts_only: false,
    status: "active",
    revision: 1,
    description: "",
    condition: "used",
    photo_urls: [],
    ...overrides
  };
}

describe("comparison table data", () => {
  it("highlights differing prices only when their source currencies match", () => {
    const [price] = buildComparisonRows([
      listing({ price: { amount: "10000", currency: "BYN" } }),
      listing({ id: "two", price: { amount: "12000", currency: "BYN" } })
    ]).filter((row) => row.key === "price");
    expect(price.isDifferent).toBe(true);

    const [mixedCurrencyPrice] = buildComparisonRows([
      listing({ price: { amount: "10000", currency: "BYN" } }),
      listing({ id: "three", price: { amount: "10000", currency: "USD" } })
    ]).filter((row) => row.key === "price");
    expect(mixedCurrencyPrice.isDifferent).toBe(false);
  });

  it("shows an FX equivalent separately with its date and marks missing facts explicitly", () => {
    const [price] = buildComparisonRows([
      listing({
        price: { amount: "10000", currency: "USD", display_byn: "32000", rate_date: "2026-10-18" }
      }),
      listing({ id: "two", fuel: null, price: { amount: "32000", currency: "BYN" } })
    ]).filter((row) => row.key === "price");

    expect(price.cells[0]?.value).toContain("10 000 USD");
    expect(price.cells[0]?.note).toContain("32 000 BYN");
    expect(price.cells[0]?.note).toContain("18.10.2026");

    const [fuel] = buildComparisonRows([listing({ fuel: null }), listing({ id: "two", fuel: "diesel" })]).filter((row) => row.key === "fuel");
    expect(fuel.cells[0]).toBeNull();
    expect(fuel.cells[1]?.value).toBe("Дизель");
  });

  it("marks all available values when a factual row differs", () => {
    const [transmission] = buildComparisonRows([
      listing({ transmission: "manual" }),
      listing({ id: "two", transmission: "automatic" })
    ]).filter((row) => row.key === "transmission");

    expect(transmission.isDifferent).toBe(true);
    expect(transmission.cells.map((cell) => cell?.value)).toEqual(["Механика", "Автомат"]);
  });
});
