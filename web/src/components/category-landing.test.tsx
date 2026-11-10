import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { CategoryLanding, MachineIllustration } from "@/components/category-landing";
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

  it("renders a distinct, decorative generated picture for each subcategory", () => {
    const codes = ["motorcycles", "special_equipment", "agricultural_equipment", "watercraft", "tires"] as const;
    const pairs = [
      ...codes.flatMap((code) => getListingSubcategories(code).map(({ value }) => [code, value] as const)),
      ["wheels", "alloy-wheel"] as const
    ];
    const sources = pairs.map(([code, value]) => {
      const html = renderToStaticMarkup(<MachineIllustration kind="" categoryCode={code} subcategory={value} />);
      expect(html, `${code}/${value}`).toContain('alt=""');
      expect(html, `${code}/${value}`).toContain('aria-hidden="true"');
      const src = /src="([^"]+)"/.exec(html)?.[1] ?? "";
      expect(src, `${code}/${value}`).toMatch(/^\/category-art\/[a-z-]+\/[a-z-]+\.webp$/);
      expect(existsSync(join(process.cwd(), "public", src)), src).toBe(true);
      return src;
    });
    expect(sources.length).toBe(34);
    expect(new Set(sources).size).toBe(sources.length);
  });

  it("renders nothing rather than a broken image when no picture exists", () => {
    expect(renderToStaticMarkup(<MachineIllustration kind="unknown" />)).toBe("");
    expect(renderToStaticMarkup(<MachineIllustration categoryCode="motorcycles" subcategory="unknown_kind" />)).toBe("");
  });
});
