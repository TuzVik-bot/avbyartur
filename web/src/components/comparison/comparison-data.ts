import { formatMileage, vehicleLabel } from "@/lib/format";
import type { Listing } from "@/lib/types";

export type ComparisonCell = { value: string; note?: string; comparisonKey?: string | number | boolean; currency?: string } | null;
export type ComparisonRowKey =
  | "vehicle" | "price" | "year" | "mileage" | "engine_volume" | "power" | "fuel" | "transmission" | "drive"
  | "body" | "modification" | "condition" | "equipment" | "color" | "customs" | "technical_condition"
  | "body_condition" | "location" | "district" | "call_hours" | "damaged" | "parts_only" | "exchange" | "bargaining" | "credit" | "leasing";

export type ComparisonRow = {
  key: ComparisonRowKey;
  label: string;
  cells: ComparisonCell[];
  isDifferent: boolean;
};

const optionLabels: Record<string, string> = {
  black: "Чёрный", white: "Белый", gray: "Серый", silver: "Серебристый", red: "Красный", blue: "Синий", green: "Зелёный", yellow: "Жёлтый", brown: "Коричневый", beige: "Бежевый", orange: "Оранжевый", purple: "Фиолетовый", other: "Другой",
  cleared_rb: "Оформлен в РБ (со слов продавца)", eaeu_import: "Ввезён из ЕАЭС (со слов продавца)", uncleared: "Не растаможен (со слов продавца)", unknown: "Не указано",
  good: "Исправен (со слов продавца)", needs_repair: "Требует ремонта (со слов продавца)", non_operational: "Не на ходу (со слов продавца)", minor_damage: "Есть небольшие повреждения (со слов продавца)", significant_damage: "Есть серьёзные повреждения (со слов продавца)", repaired: "Был в ремонте (со слов продавца)",
  abs: "ABS", esp: "ESP", airbags: "Подушки безопасности", air_conditioning: "Кондиционер", climate_control: "Климат-контроль", heated_seats: "Подогрев сидений", cruise_control: "Круиз-контроль", parking_sensors: "Парктроники", rear_camera: "Камера заднего вида", leather_seats: "Кожаный салон", carplay: "Apple CarPlay", android_auto: "Android Auto"
};

function formatAmount(value: string | number, currency: string) {
  const number = Number(value);
  if (!Number.isFinite(number)) return `${value} ${currency}`;
  return `${new Intl.NumberFormat("ru-BY", { maximumFractionDigits: 2 }).format(number)} ${currency}`;
}

function formatRateDate(value: string) {
  const dateOnly = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (dateOnly) return `${dateOnly[3]}.${dateOnly[2]}.${dateOnly[1]}`;
  const parsed = new Date(value);
  return Number.isFinite(parsed.getTime())
    ? new Intl.DateTimeFormat("ru-BY", { timeZone: "Europe/Minsk", day: "2-digit", month: "2-digit", year: "numeric" }).format(parsed)
    : value;
}

function textCell(value: string | null | undefined, comparisonKey?: string | number | boolean): ComparisonCell {
  if (value === null || value === undefined || value.trim() === "") return null;
  return { value, comparisonKey: comparisonKey ?? value.toLocaleLowerCase("ru") };
}

function numberCell(value: number | string | null | undefined, unit: string, decimals = 0): ComparisonCell {
  if (value === null || value === undefined || value === "") return null;
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return textCell(String(value));
  return {
    value: `${new Intl.NumberFormat("ru-BY", { maximumFractionDigits: decimals }).format(numeric)}${unit}`,
    comparisonKey: numeric
  };
}

function priceCell(listing: Listing): ComparisonCell {
  const price = listing.price;
  if (!price) return null;
  const numeric = Number(price.amount);
  const baseValue = formatAmount(price.amount, price.currency);
  const equivalent = price.display_byn || (price.display_currency === "BYN" ? price.display_amount : null);
  const note = price.currency === "USD" && equivalent && price.rate_date
    ? `≈ ${formatAmount(equivalent, "BYN")} по курсу на ${formatRateDate(price.rate_date)}`
    : undefined;
  return {
    value: baseValue,
    note,
    currency: price.currency,
    comparisonKey: Number.isFinite(numeric) ? numeric : price.amount
  };
}

function locationCell(listing: Listing): ComparisonCell {
  const city = listing.manual_city || listing.city?.name;
  const region = listing.region?.name;
  return textCell([city, region].filter(Boolean).join(", "));
}

function equipmentCell(listing: Listing): ComparisonCell {
  if (!listing.equipment?.length) return null;
  const labels = listing.equipment.map((item) => optionLabels[item] || item).sort((a, b) => a.localeCompare(b, "ru"));
  return textCell(labels.join(", "), [...labels].sort().join("|").toLocaleLowerCase("ru"));
}

type RowDefinition = { key: ComparisonRowKey; label: string; get: (listing: Listing) => ComparisonCell };
const rowDefinitions: RowDefinition[] = [
  { key: "vehicle", label: "Марка и модель", get: (listing) => textCell([listing.make?.name, listing.model?.name].filter(Boolean).join(" ")) },
  { key: "price", label: "Цена в объявлении", get: priceCell },
  { key: "year", label: "Год выпуска", get: (listing) => numberCell(listing.year, " г.") },
  { key: "mileage", label: "Пробег", get: (listing) => listing.mileage_km === null ? null : { value: formatMileage(listing.mileage_km), comparisonKey: listing.mileage_km } },
  { key: "engine_volume", label: "Объём двигателя", get: (listing) => numberCell(listing.engine_volume_l || listing.modification?.specs?.engine_l, " л", 2) },
  { key: "power", label: "Мощность", get: (listing) => numberCell(listing.power_hp ?? listing.modification?.specs?.power_hp, " л.с.") },
  { key: "fuel", label: "Топливо", get: (listing) => { const value = listing.fuel || listing.modification?.specs?.fuel; return value ? textCell(vehicleLabel(value), value) : null; } },
  { key: "transmission", label: "Коробка передач", get: (listing) => { const value = listing.transmission || listing.modification?.specs?.transmission; return value ? textCell(vehicleLabel(value), value) : null; } },
  { key: "drive", label: "Привод", get: (listing) => { const value = listing.drive || listing.modification?.specs?.drive; return value ? textCell(vehicleLabel(value), value) : null; } },
  { key: "body", label: "Тип кузова", get: (listing) => textCell(listing.body_type || listing.body_variant?.name) },
  { key: "modification", label: "Модификация", get: (listing) => textCell(listing.modification?.name) },
  { key: "condition", label: "Состояние по объявлению", get: (listing) => listing.condition ? textCell(listing.condition === "new" ? "Новый" : listing.condition === "used" ? "С пробегом" : listing.condition) : null },
  { key: "equipment", label: "Комплектация", get: equipmentCell },
  { key: "color", label: "Цвет", get: (listing) => { const value = listing.color; return value ? textCell(optionLabels[value] || value, value) : null; } },
  { key: "customs", label: "Таможенный статус", get: (listing) => { const value = listing.customs_status; return value ? textCell(optionLabels[value] || value, value) : null; } },
  { key: "technical_condition", label: "Техническое состояние (со слов продавца)", get: (listing) => { const value = listing.technical_condition; return value ? textCell(optionLabels[value] || value, value) : null; } },
  { key: "body_condition", label: "Состояние кузова (со слов продавца)", get: (listing) => { const value = listing.body_condition; return value ? textCell(optionLabels[value] || value, value) : null; } },
  { key: "location", label: "Город и область", get: locationCell },
  { key: "district", label: "Район", get: (listing) => textCell(listing.district) },
  { key: "call_hours", label: "Время звонков", get: (listing) => textCell(listing.call_hours) },
  { key: "damaged", label: "Повреждения (отметка продавца)", get: (listing) => ({ value: listing.damaged ? "Указаны" : "Не указаны", comparisonKey: listing.damaged }) },
  { key: "parts_only", label: "Продажа на запчасти", get: (listing) => ({ value: listing.parts_only ? "Да" : "Нет", comparisonKey: listing.parts_only }) },
  { key: "exchange", label: "Обмен", get: (listing) => listing.exchange == null ? null : ({ value: listing.exchange ? "Рассматривается" : "Нет", comparisonKey: listing.exchange }) },
  { key: "bargaining", label: "Торг", get: (listing) => listing.bargaining == null ? null : ({ value: listing.bargaining ? "Возможен" : "Нет", comparisonKey: listing.bargaining }) },
  { key: "credit", label: "Кредит", get: (listing) => listing.credit == null ? null : ({ value: listing.credit ? "Возможен" : "Нет", comparisonKey: listing.credit }) },
  { key: "leasing", label: "Лизинг", get: (listing) => listing.leasing == null ? null : ({ value: listing.leasing ? "Возможен" : "Нет", comparisonKey: listing.leasing }) }
];

export function buildComparisonRows(listings: Array<Listing | null>): ComparisonRow[] {
  return rowDefinitions.map((definition) => {
    const cells = listings.map((listing) => listing ? definition.get(listing) : null);
    const currencies = new Set(cells.filter((cell) => cell?.currency).map((cell) => cell!.currency));
    const currencyComparable = definition.key !== "price" || currencies.size <= 1;
    const values = new Set(cells.map((cell) => cell?.comparisonKey).filter((value) => value !== undefined));
    return {
      key: definition.key,
      label: definition.label,
      cells,
      isDifferent: currencyComparable && values.size > 1
    };
  });
}

export function hasMixedPriceCurrencies(listings: Array<Listing | null>): boolean {
  const currencies = new Set(listings.flatMap((listing) => listing?.price?.currency ? [listing.price.currency] : []));
  return currencies.size > 1;
}
