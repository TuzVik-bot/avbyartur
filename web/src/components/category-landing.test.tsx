import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { CategoryLanding } from "@/components/category-landing";
import { getListingSubcategories } from "@/lib/listing-subcategories";

vi.mock("@/components/search-route", () => ({ SearchRoute: () => null }));

describe("category landing navigation", () => {
  it.each([
    ["motorcycles", "motorcycles", "motorcycle"],
    ["special-equipment", "special_equipment", "road_construction"],
    ["agricultural-equipment", "agricultural_equipment", "livestock"],
    ["watercraft", "watercraft", "jet_ski"],
    ["tires", "tires", "passenger"]
  ])("links %s to category and subcategory search", (slug, code, subcategory) => {
    const html = renderToStaticMarkup(<CategoryLanding slug={slug} />);
    expect(html).toContain(`href="/cars?category_code=${code}&amp;subcategory=${subcategory}"`);
    expect(html).toContain(`href="/cars?category_code=${code}"`);
    expect(html).not.toMatch(/\b\d[\d ]* объявлен/);
  });

  it("routes wheels to its existing top-level category", () => {
    const html = renderToStaticMarkup(<CategoryLanding slug="tires" />);
    expect(html).toContain('href="/cars?category_code=wheels"');
    expect(html).toContain("Колёсные диски");
  });

  it("maps every visible subcategory to its own generated image", () => {
    const routes = [
      ["motorcycles", "motorcycles", "motorcycles"],
      ["special-equipment", "special_equipment", "special-equipment"],
      ["agricultural-equipment", "agricultural_equipment", "agricultural-equipment"],
      ["watercraft", "watercraft", "watercraft"],
      ["tires", "tires", "tires"]
    ] as const;
    let mapped = 0;
    for (const [slug, code, folder] of routes) {
      const html = renderToStaticMarkup(<CategoryLanding slug={slug} />);
      expect(html).not.toContain('viewBox="0 0 112 72"');
      for (const { value } of getListingSubcategories(code)) {
        const name = code === "tires" ? `${value}-tire`
          : code === "watercraft" ? ({ jet_ski: "jetski", motor: "outboard-motor", other: "other-watercraft" } as Record<string, string>)[value] || value
          : value.replace(/_/g, "-");
        expect(html).toContain(`src="/category-art/${folder}/${name}.webp"`);
        mapped += 1;
      }
    }
    const tiresHtml = renderToStaticMarkup(<CategoryLanding slug="tires" />);
    expect(tiresHtml).toContain('src="/category-art/wheels/alloy-wheel.webp"');
    expect(mapped).toBe(33);
  });
});
