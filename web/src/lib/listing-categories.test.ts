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
  it("keeps frame serial numbers optional and distinct from VIN", () => {
    for (const code of ["trucks", "buses", "motorcycles", "special_equipment", "agricultural_equipment", "trailers", "watercraft"]) {
      expect(categoryFields(code).find(f => f.key === "frame_serial_number")).toMatchObject({ label: "Номер рамы / серийный номер", required: false, maxLength: 120 });
      expect(detailPayload(code, { frame_serial_number: " FRAME-2026/42 ", vin: "1HGCM82633A004352" })).toEqual({ frame_serial_number: "FRAME-2026/42" });
    }
    expect(categoryFacts({ category_code: "special_equipment", category_details: { frame_serial_number: "FRAME-42" } } as never)).toContainEqual(["Номер рамы / серийный номер", "FRAME-42"]);
    for (const code of ["cars", "parts", "wheels", "tires"]) expect(categoryFields(code).some(f => f.key === "frame_serial_number")).toBe(false);
  });
});
it("removes incompatible characteristic aliases even without a category query", () => {
 expect(categorySearch("trucks", { season: "winter", diameter_in: "16", q: "MAN" })).toEqual({ category_code: "trucks", q: "MAN" });
});
