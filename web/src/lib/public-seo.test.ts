import { afterEach, describe, expect, it, vi } from "vitest";
import { isPublicIndexingEnabled, rootRobots } from "@/lib/pilot-visibility";
import {
  buildBreadcrumbJsonLd,
  buildListingMetadata,
  buildOpenGraph,
  buildWebsiteJsonLd,
  serializeJsonLd,
} from "@/lib/seo";
import { SITE_NAME, SITE_ORIGIN } from "@/lib/site-config";
import type { Listing } from "@/lib/types";

const PUBLIC_INDEXING_ENV = "AVTORINOK_PUBLIC_INDEXING_ENABLED";

afterEach(() => vi.unstubAllEnvs());

describe("public indexing switch", () => {
  it("stays closed by default and only accepts the exact true value", () => {
    for (const value of [undefined, "", "1", "TRUE", "True", "yes"]) {
      vi.stubEnv(PUBLIC_INDEXING_ENV, value as string | undefined);
      expect(isPublicIndexingEnabled()).toBe(false);
      expect(rootRobots()).toMatchObject({ index: false, follow: false, noarchive: true });
    }
  });

  it("opens root robots only for the exact true value", () => {
    vi.stubEnv(PUBLIC_INDEXING_ENV, "true");
    expect(isPublicIndexingEnabled()).toBe(true);
    expect(rootRobots()).toEqual({ index: true, follow: true });
  });
});

describe("public seo helpers", () => {
  it("builds website search action against the catalog query", () => {
    const schema = buildWebsiteJsonLd();
    expect(schema["@type"]).toBe("WebSite");
    expect(schema.potentialAction).toMatchObject({
      "@type": "SearchAction",
      target: { urlTemplate: `${SITE_ORIGIN}/cars?q={search_term_string}` },
    });
  });

  it("falls back to the brand og image when a page has none", () => {
    const og = buildOpenGraph({ title: "Страница", description: "Описание", path: "/about" });
    expect(og).toMatchObject({
      type: "website",
      siteName: SITE_NAME,
      url: `${SITE_ORIGIN}/about`,
      images: [{ url: "/og-default.jpg", width: 1200, height: 630 }],
    });
  });

  it("keeps only same-origin photo paths in og images", () => {
    const og = buildOpenGraph({
      title: "Объявление",
      description: "Описание",
      path: "/cars/bmw/3-series/listing-1",
      images: ["/api/v1/photos/one", "https://cdn.example.com/steal.jpg", "//evil.host/x", "two"],
    });
    expect(og.images).toEqual([{ url: `${SITE_ORIGIN}/api/v1/photos/one` }]);
  });

  it("numbers breadcrumb items from one", () => {
    const schema = buildBreadcrumbJsonLd([
      { name: "Главная", path: "/" },
      { name: "Автомобили", path: "/cars" },
    ]);
    expect(schema.itemListElement).toEqual([
      { "@type": "ListItem", position: 1, name: "Главная", item: `${SITE_ORIGIN}/` },
      { "@type": "ListItem", position: 2, name: "Автомобили", item: `${SITE_ORIGIN}/cars` },
    ]);
  });

  it("serializes json-ld without raw closing tags", () => {
    expect(serializeJsonLd({ name: "</script><script>alert(1)</script>" })).not.toContain("</script>");
  });

  it("adds open graph and twitter metadata to active listing pages", () => {
    const listing = {
      id: "listing-1",
      slug: "listing-1",
      title: "BMW 3 Series 2019",
      status: "active",
      make: { id: "make-1", slug: "bmw", name: "BMW" },
      model: { id: "model-1", slug: "3-series", name: "3 Series" },
      year: 2019,
      mileage_km: 88000,
      city: { id: "city-1", slug: "minsk", name: "Минск" },
      cover_url: "/api/v1/photos/cover",
      photo_urls: ["/api/v1/photos/cover", "/api/v1/photos/two"],
      price: { amount: "45000", currency: "BYN" },
    } as unknown as Listing;

    const metadata = buildListingMetadata(listing);
    expect(metadata.openGraph).toMatchObject({
      title: "BMW 3 Series 2019",
      url: `${SITE_ORIGIN}/cars/bmw/3-series/listing-1`,
      images: [
        { url: `${SITE_ORIGIN}/api/v1/photos/cover` },
        { url: `${SITE_ORIGIN}/api/v1/photos/two` },
      ],
    });
    expect(metadata.twitter).toMatchObject({ card: "summary_large_image", images: ["/api/v1/photos/cover", "/api/v1/photos/two"] });
    expect(metadata.robots).toBeUndefined();
  });
});
