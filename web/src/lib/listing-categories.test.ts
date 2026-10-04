import { describe, expect, it } from "vitest";
import { categories, categoryFields, categoryFacts, categorySearch, detailPayload } from "./listing-categories";
describe("category UI contracts", () => {
  it("forces route category and drops foreign characteristics", () => {
    expect(categorySearch("trucks", { category_code: "tires", q: "Volvo", season: "winter", make_id: "car-make" })).toEqual({ category_code: "trucks", q: "Volvo" });
    expect(categorySearch("cars", { category_code: "trucks", condition: "used" })).toEqual({ category_code: "cars", condition: "used" });
  });
  it("has every supplied section with its stable route", () => {
    expect(categories.map(c => c.label)).toEqual(["С пробегом", "Новые", "Грузовики", "Автобусы", "Мототехника", "Спецтехника", "Сельхозтехника", "Прицепы", "Водный транспорт", "Запчасти", "Диски", "Шины"]);
    expect(categories[0].href).toBe("/cars?condition=used");
  });
  it("converts numeric category details and omits empty inputs", () => {
    expect(detailPayload("tires", { width_mm: "205", profile_percent: "55", diameter_in: "16", season: "winter", quantity: "" })).toEqual({ width_mm: 205, profile_percent: 55, diameter_in: 16, season: "winter" });
    expect(categoryFields("wheels").filter(f => f.required).map(f => f.key)).toEqual(["diameter_in", "width_in", "bolt_holes", "pcd_mm"]);
  });
  it("shows operating hours instead of car mileage for equipment", () => {
    expect(categoryFacts({ category_code: "special_equipment", category_details: { operating_hours: 125 }, year: 2020 } as never)).toContainEqual(["Моточасы", "125 ч"]);
    expect(categoryFacts({ category_code: "tires", category_details: { season: "winter", diameter_in: 16 }, condition: "used" } as never)).toContainEqual(["Состояние", "Б/у"]);
  });
});
it("removes incompatible characteristic aliases even without a category query", () => {
 expect(categorySearch("trucks", { season: "winter", diameter_in: "16", q: "MAN" })).toEqual({ category_code: "trucks", q: "MAN" });
});
