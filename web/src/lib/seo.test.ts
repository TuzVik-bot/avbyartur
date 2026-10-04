import { describe, expect, it } from "vitest";
import { buildListingMetadata, buildVehicleJsonLd, serializeJsonLd } from "@/lib/seo";
import { SITE_ORIGIN } from "@/lib/site-config";
import type { Listing } from "@/lib/types";

function activeListing(overrides: Partial<Listing> = {}): Listing {
  return {
    id: "listing-1",
    slug: "bmw-320",
    title: "BMW 320",
    make: { id: "make-1", slug: "bmw", name: "BMW" },
    model: { id: "model-1", slug: "3-series", name: "3 Series" },
    generation: null,
    year: 2020,
    mileage_km: 45_000,
    fuel: "petrol",
    transmission: "automatic",
    drive: "rear",
    body_type: "sedan",
    body_variant_id: null,
    body_variant: null,
    price: { amount: "25000.00", currency: "USD" },
    region: { id: "region-1", slug: "minsk-region", name: "Минская область" },
    city: { id: "city-1", slug: "minsk", name: "Минск" },
    manual_city: null,
    cover_url: "/api/v1/photos/photo-1/768",
    photo_urls: ["/api/v1/photos/photo-1/768", "//attacker.invalid/image.jpg", "javascript:alert(1)"],
    seller: { type: "private", id: "seller-1", name: "Продавец" },
    created_at: "2026-09-30T10:00:00Z",
    updated_at: "2026-09-30T11:00:00Z",
    damaged: false,
    parts_only: false,
    status: "active",
    revision: 3,
    description: "Не включать пользовательский текст или контакты в schema.",
    condition: "used",
    contact_phone: "+375291234567",
    ...overrides,
  };
}

describe("public listing SEO data", () => {
  it("builds a self-canonical from public vehicle route fields", () => {
    const metadata = buildListingMetadata(activeListing());
    expect(metadata).toMatchObject({
      title: "BMW 320",
      alternates: { canonical: `${SITE_ORIGIN}/cars/bmw/3-series/listing-1` },
    });
    expect(metadata.description).not.toContain("Не включать пользовательский текст");
  });

  it("uses category-specific canonical and copy for non-car listings", () => {
    const listing = activeListing({ category_code: "trucks", make: null, model: null });

    const metadata = buildListingMetadata(listing);

    expect(metadata.alternates?.canonical).toBe(`${SITE_ORIGIN}/trucks/bmw-320/listing-1`);
    expect(metadata.description).toContain("разделе «Грузовики»");
    expect(metadata.description).not.toContain("автомобиле");
    expect(buildVehicleJsonLd(listing)).toBeNull();
  });

  it("emits only public vehicle facts for active listings and excludes private contact data", () => {
    const jsonLd = buildVehicleJsonLd(activeListing());
    expect(jsonLd).toMatchObject({
      "@context": "https://schema.org",
      "@type": "Car",
      name: "BMW 320",
      url: `${SITE_ORIGIN}/cars/bmw/3-series/listing-1`,
      brand: { "@type": "Brand", name: "BMW" },
      model: "3 Series",
      vehicleModelDate: "2020",
      mileageFromOdometer: { "@type": "QuantitativeValue", value: 45_000, unitCode: "KMT" },
      offers: { "@type": "Offer", price: "25000.00", priceCurrency: "USD" },
      image: [`${SITE_ORIGIN}/api/v1/photos/photo-1/768`],
    });
    expect(JSON.stringify(jsonLd)).not.toContain("contact_phone");
    expect(JSON.stringify(jsonLd)).not.toContain("+375291234567");
  });

  it("keeps sold listings visible without indexing them", () => {
    const metadata = buildListingMetadata(activeListing({ status: "sold" }));

    expect(buildVehicleJsonLd(activeListing({ status: "sold" }))).toBeNull();
    expect(metadata.robots).toEqual({
      index: false,
      follow: false,
      noarchive: true,
      googleBot: { index: false, follow: false, noimageindex: true },
    });
    expect(metadata.alternates).toEqual({ canonical: `${SITE_ORIGIN}/cars/bmw/3-series/listing-1` });
  });

  it("does not emit vehicle schema for inactive listings", () => {
    expect(buildVehicleJsonLd(activeListing({ status: "paused" }))).toBeNull();
    expect(buildListingMetadata(activeListing({ status: "paused" }))).toEqual({});
  });

  it("escapes script-breaking characters before rendering JSON-LD", () => {
    const serialized = serializeJsonLd({ name: "</script><script>alert(1)</script>" });
    expect(serialized).not.toContain("</script>");
    expect(serialized).toContain("\\u003c/script>");
  });
});
