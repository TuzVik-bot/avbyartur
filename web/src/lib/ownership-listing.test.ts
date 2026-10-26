import { describe, expect, it } from "vitest";
import { ownershipNeedsCurrentRate, ownershipSeedFromListing, parseOwnershipListingId } from "@/lib/ownership-listing";
import type { Listing } from "@/lib/types";
import { SITE_ORIGIN } from "@/lib/site-config";

const id = "123e4567-e89b-42d3-a456-426614174000";
const listing = {
  id, slug: "listing", title: "Tesla Model 3", make: { id: "m", slug: "tesla", name: "Tesla" }, model: { id: "x", slug: "model-3", name: "Model 3" },
  year: 2021, mileage_km: 40000, fuel: "electric", price: { amount: "25000", currency: "USD", display_byn: null, rate_date: null },
} as Listing;

describe("ownership listing adapter", () => {
  it("accepts UUIDs and canonical same-site paths, but rejects external URLs and malformed ids", () => {
    expect(parseOwnershipListingId(id)).toBe(id);
    expect(parseOwnershipListingId(`/cars/tesla/model-3/${id}`)).toBe(id);
    expect(parseOwnershipListingId(`${SITE_ORIGIN}/cars/tesla/model-3/${id}`)).toBe(id);
    const productionOrigin = "https://xn--80aeylebmo7f.xn--90ais";
    expect(parseOwnershipListingId(`${productionOrigin}/cars/tesla/model-3/${id}`, productionOrigin)).toBe(id);
    expect(parseOwnershipListingId(`https://attacker.example/cars/tesla/model-3/${id}`, productionOrigin)).toBeNull();
    expect(parseOwnershipListingId(`https://attacker.example/cars/tesla/model-3/${id}`)).toBeNull();
    expect(parseOwnershipListingId("https://av.by/cars/tesla/model-3/not-an-id")).toBeNull();
  });

  it("does not invent a BYN price or consumption and records its energy source", () => {
    const seed = ownershipSeedFromListing(listing);
    expect(seed.input).toMatchObject({ energyType: "electric" });
    expect(seed.input.priceByn).toBeUndefined();
    expect(seed.input.electricityKwhPer100Km).toBeUndefined();
    expect(seed.provenance.join(" ")).toContain("BYN-эквивалент и текущий курс недоступны");
    expect(seed.provenance.join(" ")).toContain("предварительные значения калькулятора — изменяемый пример");
  });

  it("uses the official response rate only when the listing has no dated BYN display", () => {
    const seed = ownershipSeedFromListing(listing, {
      rate_date: "2026-10-26",
      rates: [{ currency: "USD", official_rate: "3.1", scale: 1, byn_per_unit: "3.1" }]
    });
    expect(seed.input.priceByn).toBe(77500);
    expect(seed.input.resaleByn).toBe(46500);
    expect(seed.provenance.join(" ")).toContain("курс 3.1 BYN за USD на 2026-10-26");
  });

  it("rounds seeded price and illustrative resale to cents", () => {
    const seed = ownershipSeedFromListing({
      ...listing,
      price: { amount: "13442.07", currency: "BYN" }
    });
    expect(seed.input.priceByn).toBe(13442.07);
    expect(seed.input.resaleByn).toBe(8065.24);
  });

  it("rounds a fractional-rate USD conversion to cents before deriving resale", () => {
    const seed = ownershipSeedFromListing({
      ...listing,
      price: { amount: "10000.01", currency: "USD", display_byn: null, rate_date: null }
    }, {
      rate_date: "2026-10-26",
      rates: [{ currency: "USD", official_rate: "3.217", scale: 1, byn_per_unit: "3.217" }]
    });
    expect(seed.input.priceByn).toBe(32170.03);
    expect(seed.input.resaleByn).toBe(19302.02);
  });

  it("falls back to the current official rate when the saved BYN display or its date is malformed", () => {
    const malformed = { ...listing, price: { ...listing.price!, display_byn: "not-a-number", rate_date: "2026-02-30" } };
    expect(ownershipNeedsCurrentRate(malformed)).toBe(true);
    const seed = ownershipSeedFromListing(malformed, {
      rate_date: "2026-10-26",
      rates: [{ currency: "USD", official_rate: "3.1", scale: 1, byn_per_unit: "3.1" }]
    });
    expect(seed.input.priceByn).toBe(77500);
    expect(seed.provenance.join(" ")).toContain("курс 3.1 BYN за USD на 2026-10-26");
  });

  it("does not use an invalid current rate date", () => {
    const seed = ownershipSeedFromListing(listing, {
      rate_date: "2026-02-30",
      rates: [{ currency: "USD", official_rate: "3.1", scale: 1, byn_per_unit: "3.1" }]
    });
    expect(seed.input.priceByn).toBeUndefined();
  });

  it("marks a dated listing conversion as potentially stale", () => {
    const seed = ownershipSeedFromListing({ ...listing, price: { ...listing.price!, display_byn: "31000", rate_date: "2020-01-01" } });
    expect(seed.input.priceByn).toBe(31000);
    expect(seed.provenance.join(" ")).toContain("курс объявления может быть устаревшим");
  });

  it("uses hybrid as fuel and only marks a listing as electric for its explicit electric fuel", () => {
    const hybrid = ownershipSeedFromListing({ ...listing, fuel: "hybrid" });
    expect(hybrid.input.energyType).toBe("fuel");
    expect(hybrid.provenance.join(" ")).toContain("расход, тарифы и содержание не указаны в объявлении");
    expect(ownershipSeedFromListing({ ...listing, fuel: "petrol" }).input.energyType).toBe("fuel");
    expect(ownershipSeedFromListing({ ...listing, fuel: "plugin_hybrid" }).input.energyType).toBe("plugin_hybrid");
  });
});
