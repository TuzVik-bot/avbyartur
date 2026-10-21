import type { ListingSearch } from "@/lib/types";
import { searchUrl } from "@/lib/search-state";

export type UseCaseEditor = "condition" | "photos" | "fuel" | "none";

export type UseCasePreset = {
  slug: string;
  title: string;
  description: string;
  note: string;
  editor: UseCaseEditor;
  defaults: ListingSearch;
};

export const useCasePresets: readonly UseCasePreset[] = [
  {
    slug: "first-car",
    title: "Первый автомобиль",
    description: "Начните с автомобилей с пробегом, а затем задайте свой диапазон цены и года выпуска.",
    note: "Подборка не проверяет историю или техническое состояние. Сравните документы и предусмотрите независимую диагностику.",
    editor: "condition",
    defaults: { category_code: "cars", condition: "used" },
  },
  {
    slug: "family",
    title: "Для семьи",
    description: "Откройте объявления с фотографиями и выберите подходящий кузов и оснащение в карточках.",
    note: "Фотографии помогают рассмотреть автомобиль, но сами по себе ничего не говорят о его техническом состоянии.",
    editor: "photos",
    defaults: { category_code: "cars", has_photos: "true" },
  },
  {
    slug: "economical",
    title: "Сравнить электромобили",
    description: "Посмотрите автомобили с электрическим типом двигателя и задайте свой предел цены и года.",
    note: "Тип двигателя не подтверждает меньшую общую стоимость владения: учитывайте цену покупки, зарядку и условия использования.",
    editor: "fuel",
    defaults: { category_code: "cars", fuel: "electric" },
  },
  {
    slug: "work",
    title: "Для работы и перевозок",
    description: "Начальный выбор — грузовая категория. Для рабочих поездок без перевозки груза переключите категорию на легковые автомобили.",
    note: "Выберите тип транспорта под задачу: фильтры не оценивают грузоподъёмность, пригодность или состояние конкретной машины.",
    editor: "none",
    defaults: { category_code: "trucks" },
  },
];

export type UseCaseFilterState = {
  categoryCode: string;
  condition: string;
  fuel: string;
  hasPhotos: boolean;
  yearFrom: string;
  priceTo: string;
};

const categoryCodes = new Set<NonNullable<ListingSearch["category_code"]>>([
  "cars", "trucks", "buses", "motorcycles", "special_equipment", "agricultural_equipment", "trailers", "watercraft", "parts", "wheels", "tires",
]);
const fuelTypes = new Set(["petrol", "diesel", "hybrid", "electric", "lpg", "other"]);

function positiveInteger(value: string, minimum: number): string | undefined {
  const normalized = value.trim();
  if (!/^\d+$/.test(normalized)) return undefined;
  const parsed = Number(normalized);
  return Number.isSafeInteger(parsed) && parsed >= minimum ? String(parsed) : undefined;
}

export function buildUseCaseSearchHref(preset: UseCasePreset, state: UseCaseFilterState): string {
  const category = categoryCodes.has(state.categoryCode as NonNullable<ListingSearch["category_code"]>)
    ? state.categoryCode as NonNullable<ListingSearch["category_code"]>
    : undefined;
  const condition = preset.editor === "condition" && ["new", "used"].includes(state.condition)
    ? state.condition
    : undefined;
  const fuel = preset.editor === "fuel" && fuelTypes.has(state.fuel) ? state.fuel : undefined;
  const hasPhotos = preset.editor === "photos" && state.hasPhotos ? "true" : undefined;
  const yearMin = positiveInteger(state.yearFrom, 1886);
  const priceMax = positiveInteger(state.priceTo, 1);

  return searchUrl({
    ...preset.defaults,
    category_code: category,
    condition,
    fuel,
    has_photos: hasPhotos,
    year_min: yearMin,
    price_max: priceMax,
    currency: priceMax ? "BYN" : undefined,
  });
}
