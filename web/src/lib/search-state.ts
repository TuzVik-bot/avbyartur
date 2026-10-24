import type { ListingSearch } from "@/lib/types";
import { isListingSubcategory } from "@/lib/listing-subcategories";

const categoryCodes: readonly NonNullable<ListingSearch["category_code"]>[] = [
  "cars", "trucks", "buses", "motorcycles", "special_equipment", "agricultural_equipment", "trailers", "watercraft", "parts", "wheels", "tires"
];
const categoryCodeSet: ReadonlySet<string> = new Set(categoryCodes);

function isCategoryCode(value: unknown): value is NonNullable<ListingSearch["category_code"]> {
  return typeof value === "string" && categoryCodeSet.has(value);
}

const allowedSearchKeys: (keyof ListingSearch)[] = [
  "category_code", "subcategory", "q", "make_id", "model_id", "generation_id", "body_variant_id", "modification_id", "price_min", "price_max", "currency", "year_min", "year_max",
  "mileage_min", "mileage_max", "fuel", "transmission", "drive", "body_type", "damaged", "parts_only", "condition", "color", "customs_status", "technical_condition", "body_condition",
  "exchange", "bargaining", "credit", "leasing", "equipment", "district", "call_hours", "has_vin", "has_photos", "engine_volume_min", "engine_volume_max", "power_min", "power_max",
  "region_id", "city_id", "seller_type", "page", "page_size", "sort"
];

export function readSearchParams(input: URLSearchParams | Record<string, string | string[] | undefined>): ListingSearch {
  const result: ListingSearch = {};
  for (const key of allowedSearchKeys) {
    const value = input instanceof URLSearchParams ? key === "equipment" ? input.getAll(key) : input.get(key) : input[key];
    if (key === "equipment" && Array.isArray(value)) {
      const values = value.filter((item): item is string => typeof item === "string" && item.trim() !== "").map((item) => item.trim());
      if (values.length) result.equipment = values;
      continue;
    }
    const normalized = Array.isArray(value) ? value[0] : value;
    if (typeof normalized === "string" && normalized.trim() !== "") {
      const trimmed = normalized.trim();
      if (key === "category_code" && !isCategoryCode(trimmed)) continue;
      if (key === "subcategory" && (!result.category_code || !isListingSubcategory(result.category_code, trimmed))) continue;
      result[key] = trimmed as never;
    }
  }
  if ((result.price_min || result.price_max) && !result.currency) result.currency = "BYN";
  return result;
}

export function searchUrl(search: ListingSearch, patch: Partial<ListingSearch> = {}) {
  const next = { ...search, ...patch };
  const dependencies: Partial<Record<keyof ListingSearch, (keyof ListingSearch)[]>> = {
    make_id: ["model_id", "generation_id", "body_variant_id", "modification_id"],
    model_id: ["generation_id", "body_variant_id", "modification_id"],
    generation_id: ["body_variant_id", "modification_id"],
    region_id: ["city_id"],
    category_code: ["subcategory"]
  };
  for (const [parent, children] of Object.entries(dependencies) as [keyof ListingSearch, (keyof ListingSearch)[]][]) {
    if (Object.hasOwn(patch, parent)) {
      for (const child of children) {
        if (!Object.hasOwn(patch, child)) next[child] = undefined;
      }
    }
  }
  if (Object.keys(patch).some((key) => key !== "page" && key !== "page_size")) {
    next.page = undefined;
  }
  const params = new URLSearchParams();
  for (const key of allowedSearchKeys) {
    const value = next[key];
    if (key === "category_code" && !isCategoryCode(value)) continue;
    if (key === "subcategory" && (!next.category_code || !isListingSubcategory(next.category_code, value as string))) continue;
    if (Array.isArray(value)) {
      for (const entry of value) if (entry) params.append(key, entry);
    } else if (value !== undefined && value !== "") params.set(key, String(value));
  }
  const query = params.toString();
  return query ? `/cars?${query}` : "/cars";
}

export const activeSearchKeys = allowedSearchKeys.filter((key) => !["category_code", "page", "page_size", "sort", "currency"].includes(key));

const relaxationPriority: (typeof activeSearchKeys)[number][] = [
  "city_id", "region_id", "price_max", "price_min", "year_min", "year_max", "mileage_max", "mileage_min",
  "modification_id", "body_variant_id", "generation_id", "model_id", "make_id", "engine_volume_max", "engine_volume_min",
  "power_max", "power_min", "fuel", "transmission", "drive", "body_type", "condition", "seller_type", "equipment",
  "color", "customs_status", "technical_condition", "body_condition", "damaged", "parts_only", "district", "call_hours",
  "exchange", "bargaining", "credit", "leasing", "has_vin", "has_photos", "q"
];

type SearchRelaxationOption = { key: (typeof activeSearchKeys)[number] | "budget"; href: string; label?: string };

function expandedPrice(value: string | undefined, factor: number, direction: "down" | "up") {
  if (value === undefined) return undefined;
  if (!/^\d+(?:\.\d+)?$/.test(value)) return null;
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount <= 0 || amount > Number.MAX_SAFE_INTEGER) return null;
  const cents = amount * factor * 100;
  const expanded = (direction === "down" ? Math.floor(cents + 1e-8) : Math.ceil(cents - 1e-8)) / 100;
  return Number.isFinite(expanded) && expanded > 0 ? String(Number(expanded.toFixed(2))) : null;
}

export function searchRelaxationOptions(search: ListingSearch, limit = 4, priceOperationsAvailable = false): SearchRelaxationOption[] {
  const selected = new Set(activeSearchKeys.filter((key) => {
    const value = search[key];
    return Array.isArray(value) ? value.length > 0 : value !== undefined && value !== null && value !== "";
  }));
  const boundedLimit = Number.isFinite(limit) ? Math.max(0, Math.floor(limit)) : 4;

  const options: SearchRelaxationOption[] = [...new Set([...relaxationPriority, ...activeSearchKeys])]
    .filter((key) => selected.has(key))
    .slice(0, boundedLimit)
    .map((key) => ({
      key,
      href: searchUrl(search, { [key]: undefined } as Partial<ListingSearch>)
    }));

  if (priceOperationsAvailable && search.currency && ["BYN", "USD"].includes(search.currency) && (search.price_min || search.price_max)) {
    const priceMin = expandedPrice(search.price_min, 0.85, "down");
    const priceMax = expandedPrice(search.price_max, 1.15, "up");
    if (priceMin !== null && priceMax !== null && (priceMin === undefined || priceMax === undefined || Number(priceMin) <= Number(priceMax))) {
      options.push({
        key: "budget",
        href: searchUrl(search, { price_min: priceMin, price_max: priceMax }),
        label: "Расширить бюджет на 15%"
      });
    }
  }

  const unique = new Set<string>();
  return options.filter((option) => {
    if (unique.has(option.href)) return false;
    unique.add(option.href);
    return true;
  });
}

export function clearSearchFilters(search: ListingSearch) {
  const patch = Object.fromEntries(activeSearchKeys.map((key) => [key, undefined])) as Partial<ListingSearch>;
  return searchUrl(search, patch);
}
