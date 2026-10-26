import { describe, expect, it } from "vitest";
import { buildBreadcrumbJsonLd } from "./seo";
import { listingCatalogBreadcrumbs } from "./listing-breadcrumbs";

describe("listing catalog breadcrumbs", () => {
  const make = { id: "make", slug: "toyota", name: "Toyota" };
  it("opens search for snapshot makes and models instead of nonexistent manual routes", () => {
    const items = listingCatalogBreadcrumbs({
      make: { id: "zero", slug: "manual-uaz", name: "УАЗ" },
      model: { id: "zero", slug: "manual-patriot", name: "Patriot" },
    });
    expect(() => buildBreadcrumbJsonLd(items)).not.toThrow();
    expect(items.map(({ path }) => path)).toEqual([
      `/cars?q=${encodeURIComponent("УАЗ")}`,
      `/cars?q=${encodeURIComponent("УАЗ")}+Patriot`,
    ]);
  });
  it("keeps exact catalog routes for known makes and models", () => {
    expect(listingCatalogBreadcrumbs({ make, model: { id: "model", slug: "corolla", name: "Corolla" } }).map(({ path }) => path))
      .toEqual(["/cars/toyota", "/cars/toyota/corolla"]);
  });
  it("retains the make filter when only the model is entered manually", () => {
    const items = listingCatalogBreadcrumbs({ make, model: { id: "make", slug: "manual-model", name: "Rare model" } });
    const url = new URL(items[1].path, "https://example.test");
    expect(url.pathname).toBe("/cars");
    expect(url.searchParams.get("make_id")).toBe("make");
    expect(url.searchParams.get("q")).toBe("Rare model");
  });
});
