import type { ListingSearch } from "@/lib/types";

export type ListingCategoryCode = NonNullable<ListingSearch["category_code"]>;
export type ListingSubcategory = { value: string; label: string };

export const LISTING_SUBCATEGORIES: Partial<Record<ListingCategoryCode, readonly ListingSubcategory[]>> = {
  motorcycles: [
    { value: "motorcycle", label: "Мотоцикл" }, { value: "scooter", label: "Скутер" },
    { value: "atv", label: "Квадроцикл" }, { value: "snowmobile", label: "Снегоход" },
  ],
  special_equipment: [
    { value: "road_construction", label: "Дорожно-строительная" }, { value: "municipal", label: "Коммунальная" },
    { value: "crane", label: "Крановая" }, { value: "forestry", label: "Лесная" }, { value: "loader", label: "Погрузчик" },
    { value: "lift", label: "Подъемная" }, { value: "concrete", label: "Бетонная" }, { value: "tow_truck", label: "Эвакуатор" },
    { value: "excavator", label: "Экскаватор" }, { value: "other", label: "Другая спецтехника" },
  ],
  agricultural_equipment: [
    { value: "livestock", label: "Животноводство" }, { value: "mini", label: "Мини-техника" },
    { value: "soil_preparation", label: "Подготовка почвы" }, { value: "sowing", label: "Посевная" },
    { value: "post_harvest", label: "Послеуборочная" }, { value: "other_harvest", label: "Прочая уборочная" },
    { value: "grain_harvest", label: "Зерноуборочная" }, { value: "forage_harvest", label: "Кормоуборочная" },
    { value: "vegetable_harvest", label: "Овощная уборочная" }, { value: "tractor", label: "Трактор" },
    { value: "crop_care", label: "Уход за посевами" }, { value: "other", label: "Другая сельхозтехника" },
  ],
  watercraft: [
    { value: "jet_ski", label: "Гидроцикл" }, { value: "boat", label: "Лодка" },
    { value: "motor", label: "Мотор" }, { value: "other", label: "Другой водный транспорт" },
  ],
  tires: [
    { value: "passenger", label: "Легковые" }, { value: "truck", label: "Грузовые" },
    { value: "motorcycle", label: "Мотоциклетные" },
  ],
};

export function getListingSubcategories(categoryCode: ListingCategoryCode): readonly ListingSubcategory[] {
  return LISTING_SUBCATEGORIES[categoryCode] ?? [];
}

export function isListingSubcategory(categoryCode: ListingCategoryCode, value: string): boolean {
  return getListingSubcategories(categoryCode).some((item) => item.value === value);
}

export function listingSubcategoryDetailsField(categoryCode: ListingCategoryCode): "vehicle_type" | "equipment_type" | "watercraft_type" | null {
  if (["motorcycles", "tires"].includes(categoryCode)) return "vehicle_type";
  if (["special_equipment", "agricultural_equipment"].includes(categoryCode)) return "equipment_type";
  if (categoryCode === "watercraft") return "watercraft_type";
  return null;
}
