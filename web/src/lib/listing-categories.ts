import type { ListingSearch, ListingSummary } from "./types";
import { formatMileage, vehicleLabel } from "./format";
export type CategoryCode = NonNullable<ListingSearch["category_code"]>;
export const categories: { code: CategoryCode; label: string; href: string }[] = [
  { code: "cars", label: "С пробегом", href: "/cars?condition=used" }, { code: "cars", label: "Новые", href: "/cars?condition=new" },
  ...([ ["trucks", "Грузовики"], ["buses", "Автобусы"], ["motorcycles", "Мототехника"], ["special_equipment", "Спецтехника"], ["agricultural_equipment", "Сельхозтехника"], ["trailers", "Прицепы"], ["watercraft", "Водный транспорт"], ["parts", "Запчасти"], ["wheels", "Диски"], ["tires", "Шины"] ] as [CategoryCode, string][]).map(([code, label]) => ({ code, label, href: `/${code.replaceAll("_", "-")}` }))
];
export const categoryPath = (code: string) => `/${code.replaceAll("_", "-")}`;
export const isGoods = (code: string) => ["parts", "wheels", "tires"].includes(code);
export const hasMileage = (code: string) => ["cars", "trucks", "buses", "motorcycles"].includes(code);
export type CategoryField = { key: string; label: string; type?: "number"; required?: boolean; options?: Record<string, string>; min?: number; max?: number; step?: string; maxLength?: number };
const number = (key: string, label: string, required = false, max?: number, min = 0, step = "1"): CategoryField => ({ key, label, type: "number", required, max, min, step });
const text = (key: string, label: string, required = false, maxLength = 80): CategoryField => ({ key, label, required, maxLength });
const other = { other: "Другое" };
const fields: Record<CategoryCode, CategoryField[]> = {
 cars: [],
 trucks: [{ key: "vehicle_type", label: "Тип грузовика", required: true, options: { truck: "Грузовик", tractor_unit: "Тягач", van: "Фургон", ...other } }, number("payload_kg", "Грузоподъёмность, кг"), number("gross_weight_kg", "Полная масса, кг"), text("axle_configuration", "Колёсная формула", false, 32)],
 buses: [{ key: "vehicle_type", label: "Тип автобуса", required: true, options: { bus: "Автобус", minibus: "Микроавтобус", coach: "Туристический автобус", ...other } }, number("seats", "Количество мест", false, 500), text("engine_type", "Тип двигателя", false, 40)],
 motorcycles: [{ key: "vehicle_type", label: "Тип мототехники", required: true, options: { motorcycle: "Мотоцикл", scooter: "Скутер", atv: "Квадроцикл", snowmobile: "Снегоход", ...other } }, number("engine_volume_cc", "Объём двигателя, см³", false, 10000), number("power_hp", "Мощность, л.с.", false, 3000)],
 special_equipment: [text("equipment_type", "Тип спецтехники", true), number("operating_hours", "Моточасы"), number("weight_kg", "Масса, кг"), number("payload_kg", "Грузоподъёмность, кг")],
 agricultural_equipment: [text("equipment_type", "Тип сельхозтехники", true), number("operating_hours", "Моточасы"), number("power_hp", "Мощность, л.с.", false, 3000), number("working_width_m", "Рабочая ширина, м", false, 100, 0, "any")],
 trailers: [text("trailer_type", "Тип прицепа", true), number("axles", "Количество осей", false, 20), number("payload_kg", "Грузоподъёмность, кг"), number("gross_weight_kg", "Полная масса, кг")],
 watercraft: [text("watercraft_type", "Тип водного транспорта", true), number("length_m", "Длина, м", false, 200, 0, "any"), text("hull_material", "Материал корпуса"), number("motor_power_hp", "Мощность мотора, л.с.", false, 3000)],
 parts: [text("part_group", "Группа запчастей", true, 120), text("manufacturer", "Производитель", false, 120), text("part_number", "Номер детали", false, 120), text("compatibility", "Совместимость", false, 500), number("quantity", "Количество")],
 wheels: [number("diameter_in", "Диаметр, дюймы", true, 40, 0.01, "any"), number("width_in", "Ширина, дюймы", true, 30, 0.01, "any"), number("bolt_holes", "Количество отверстий", true, 12, 1), number("pcd_mm", "PCD, мм", true, 300, 0.01, "any"), number("offset_et", "Вылет ET", false, 200, -200, "any"), number("dia_mm", "DIA, мм", false, 300, 0, "any"), { key: "material", label: "Материал", options: { steel: "Стальные", alloy: "Литые", forged: "Кованые", ...other } }, number("quantity", "Количество", false, 100)],
 tires: [number("width_mm", "Ширина, мм", true, 1000, 1), number("profile_percent", "Профиль, %", true, 100, 1), number("diameter_in", "Диаметр, дюймы", true, 40, 0.01, "any"), { key: "season", label: "Сезон", required: true, options: { summer: "Летние", winter: "Зимние", all_season: "Всесезонные" } }, number("load_index", "Индекс нагрузки", false, 1000), text("speed_index", "Индекс скорости", false, 8), number("quantity", "Количество", false, 100)]
};
const frameSerialNumber = text("frame_serial_number", "Номер рамы / серийный номер", false, 120);
for (const code of ["trucks", "buses", "motorcycles", "special_equipment", "agricultural_equipment", "trailers", "watercraft"] as const) fields[code].push(frameSerialNumber);
export const categoryFields = (code: string) => fields[code as CategoryCode] || [];
export function detailPayload(code: string, values: Record<string, string>) {
 return Object.fromEntries(categoryFields(code).filter(f => values[f.key]?.trim()).map(f => [f.key, f.type === "number" ? Number(values[f.key]) : values[f.key].trim()]));
}
export function categorySearch(code: CategoryCode, search: ListingSearch): ListingSearch {
 const next = { ...search, category_code: code };
 if (code !== "cars") for (const key of ["make_id", "model_id", "generation_id", "body_variant_id", "modification_id", "body_type"] as const) delete next[key];
 if ((search.category_code && search.category_code !== code) || code === "cars") for (const key of ["details", "subtype", "diameter_in", "width_mm", "season"] as const) delete next[key];
 for (const alias of ["diameter_in", "width_mm", "season"] as const) if (!categoryFields(code).some(field => field.key === alias)) delete next[alias];
 if (!["trucks", "buses", "motorcycles", "special_equipment", "agricultural_equipment", "trailers", "watercraft", "parts"].includes(code)) delete next.subtype;
 return next;
}
export function categoryFacts(listing: Pick<ListingSummary, "category_code" | "category_details" | "year" | "condition" | "mileage_km" | "fuel" | "transmission">): string[][] {
 const code = listing.category_code || "cars";
 const facts: string[][] = [];
 if (!isGoods(code)) facts.push(["Год выпуска", listing.year ? `${listing.year} г.` : "Не указан"]);
 if (hasMileage(code)) facts.push(["Пробег", formatMileage(listing.mileage_km)]);
 if (code === "cars") facts.push(["Топливо", vehicleLabel(listing.fuel)], ["Коробка передач", vehicleLabel(listing.transmission)]);
 for (const f of categoryFields(code)) {
  const value = listing.category_details?.[f.key];
  if (value !== undefined && value !== null && value !== "") facts.push([f.label, f.options?.[String(value)] || `${value}${f.key === "operating_hours" ? " ч" : ""}`]);
 }
 facts.push(["Состояние", listing.condition === "new" ? "Новый" : listing.condition === "used" ? (isGoods(code) ? "Б/у" : "С пробегом") : "Не указано"]);
 return facts;
}
