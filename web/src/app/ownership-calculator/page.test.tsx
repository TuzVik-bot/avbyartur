import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Listing } from "@/lib/types";
import { SITE_ORIGIN } from "@/lib/site-config";

const mocks = vi.hoisted(() => ({ listing: vi.fn(), customsRates: vi.fn() }));
vi.mock("@/lib/server-api", () => ({ serverApi: mocks }));
vi.mock("@/components/ownership-calculator", () => ({ OwnershipCalculator: (props: { initialVehicles?: { id: string; title: string; input: Record<string, unknown> }[]; notices?: string[] }) => createElement("div", { "data-seeds": JSON.stringify(props.initialVehicles), "data-notices": props.notices?.join("|") }) }));

import OwnershipCalculatorPage from "@/app/ownership-calculator/page";

const idOne = "123e4567-e89b-42d3-a456-426614174000";
const idTwo = "123e4567-e89b-42d3-a456-426614174001";
const publicListing = (id: string, title: string): Listing => ({
  id, slug: "listing", title, make: { id: "m", slug: "toyota", name: "Toyota" }, model: { id: "x", slug: "prius", name: "Prius" }, generation: null,
  year: 2020, mileage_km: 10000, fuel: "hybrid", transmission: "automatic", drive: "front", price: { amount: "20000", currency: "BYN" }, region: null, city: null,
  seller: { type: "private", id: "seller-id", name: "Private seller" }, created_at: "", updated_at: "", damaged: false, parts_only: false,
} as Listing);

describe("ownership calculator route", () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it("loads only validated listing UUIDs and serializes only calculator seed fields", async () => {
    mocks.listing.mockImplementation(async (id: string) => ({ listing: publicListing(id, id === idOne ? "Toyota Prius" : "Toyota Prius comparison") }));
    const page = await OwnershipCalculatorPage({ searchParams: Promise.resolve({ listing: idOne, compare: `${SITE_ORIGIN}/cars/toyota/prius/${idTwo}` }) });
    const html = renderToStaticMarkup(page);
    expect(mocks.listing.mock.calls.map(([id]) => id)).toEqual([idOne, idTwo]);
    expect(html).toContain("Стоимость владения автомобилем");
    expect(html).toContain("Toyota Prius");
    expect(html).not.toContain("seller-id");
    expect(mocks.customsRates).not.toHaveBeenCalled();
  });

  it("does not call the listing API for invalid input and keeps manual calculation available", async () => {
    const page = await OwnershipCalculatorPage({ searchParams: Promise.resolve({ listing: "https://attacker.invalid/" + idOne }) });
    const html = renderToStaticMarkup(page);
    expect(mocks.listing).not.toHaveBeenCalled();
    expect(html).toContain("Не удалось распознать ссылку");
    expect(html).toContain("расчёт вручную доступен ниже");
  });

  it("uses a current official USD rate only when the listing has no dated BYN display", async () => {
    mocks.listing.mockResolvedValue({ listing: { ...publicListing(idOne, "Tesla"), fuel: "electric", price: { amount: "10000", currency: "USD", display_byn: null, rate_date: null } } });
    mocks.customsRates.mockResolvedValue({ rate_date: "2026-10-26", rates: [{ currency: "USD", official_rate: "3.2", scale: 1, byn_per_unit: "3.2" }] });
    const page = await OwnershipCalculatorPage({ searchParams: Promise.resolve({ listing: idOne }) });
    const html = renderToStaticMarkup(page);
    expect(mocks.customsRates).toHaveBeenCalledOnce();
    expect(html).toContain("electric");
    expect(html).toContain("32000");
  });
});
