import { describe, expect, it } from "vitest";
import { matchesCatalogSearch } from "./catalog-search";

describe("progressive catalog search", () => {
  it("narrows results as more characters are entered", () => {
    const items = ["Skoda", "Subaru", "Volvo"].map((name) => ({ id: name, slug: name, name }));
    expect(items.filter((item) => matchesCatalogSearch(item, "s")).map((item) => item.name)).toEqual(["Skoda", "Subaru"]);
    expect(items.filter((item) => matchesCatalogSearch(item, "sk")).map((item) => item.name)).toEqual(["Skoda"]);
  });

  it("matches aliases, accents, case and surrounding whitespace", () => {
    const item = { id: "skoda", slug: "skoda", name: "Škoda", aliases: ["Шкода"] };
    expect(matchesCatalogSearch(item, " SKO ")).toBe(true);
    expect(matchesCatalogSearch(item, "шк")).toBe(true);
    expect(matchesCatalogSearch(item, "volvo")).toBe(false);
  });

  it("shows all choices when the search is cleared", () => {
    expect(matchesCatalogSearch({ id: "x", slug: "x", name: "Volvo" }, "")).toBe(true);
  });
});
