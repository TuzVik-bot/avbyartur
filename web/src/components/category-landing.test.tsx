import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { CategoryLanding, MachineIllustration } from "@/components/category-landing";

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

  it("renders distinct, decorative SVG silhouettes for each subcategory illustration", () => {
    const variants = [
      ...Array.from({ length: 4 }, (_, index) => renderToStaticMarkup(<MachineIllustration kind="moto" index={index} />)),
      ...Array.from({ length: 12 }, (_, index) => renderToStaticMarkup(<MachineIllustration kind="agri" index={index} />)),
      ...Array.from({ length: 10 }, (_, index) => renderToStaticMarkup(<MachineIllustration kind="special" index={index} />)),
      ...Array.from({ length: 4 }, (_, index) => renderToStaticMarkup(<MachineIllustration kind="water" index={index} />)),
      ...Array.from({ length: 4 }, (_, index) => renderToStaticMarkup(<MachineIllustration kind="tires" index={index} />))
    ];
    expect(new Set(variants).size).toBe(variants.length);
    expect(variants.every((svg) => svg.includes('aria-hidden="true"') && svg.includes('viewBox="0 0 112 72"'))).toBe(true);
  });
});
