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
  "category_code", "subcategory", "q", "make_id", "model_id", "make_ids", "model_ids", "generation_id", "body_variant_id", "modification_id", "price_min", "price_max", "currency", "year_min", "year_max",
  "mileage_min", "mileage_max", "fuel", "transmission", "drive", "body_type", "damaged", "parts_only", "in_transit", "condition", "color", "customs_status", "technical_condition", "body_condition",
  "exchange", "bargaining", "credit", "leasing", "equipment", "district", "call_hours", "has_vin", "has_photos", "engine_volume_min", "engine_volume_max", "power_min", "power_max",
  "region_id", "city_id", "seller_type", "page", "page_size", "sort"
];

// Limit catalog fan-out before using identifiers from a URL.
export function catalogIds(value?: string): string[] {
  if (!value) return [];
  const ids = value.split(",");
  const uuid = /^(?:[0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i;
  if (ids.length > 50 || ids.some((id) => !uuid.test(id.trim()))) return [];
  return [...new Set(ids.map((id) => id.trim()))];
}

export function readSearchParams(input: URLSearchParams | Record<string, string | string[] | undefined>): ListingSearch {
  const result: ListingSearch = {};
  for (const key of allowedSearchKeys) {
    const value = input instanceof URLSearchParams ? key === "equipment" ? input.getAll(key) : input.get(key) : input[key];
    if (key === "equipment") {
      const values = (Array.isArray(value) ? value : [value])
        .filter((item): item is string => typeof item === "string" && item.trim() !== "")
        .map((item) => item.trim());
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
  if (catalogIds(result.make_ids || result.make_id).length > 1 || catalogIds(result.model_ids || result.model_id).length > 1) {
    delete result.generation_id;
    delete result.body_variant_id;
    delete result.modification_id;
  }
  return result;
}

export function searchUrl(search: ListingSearch, patch: Partial<ListingSearch> = {}) {
  const next = { ...search, ...patch };
  if (Object.hasOwn(patch, "make_ids")) next.make_id = undefined;
  if (Object.hasOwn(patch, "model_ids")) next.model_id = undefined;
  if (Object.hasOwn(patch, "make_id")) next.make_ids = undefined;
  if (Object.hasOwn(patch, "model_id")) next.model_ids = undefined;
  const dependencies: Partial<Record<keyof ListingSearch, (keyof ListingSearch)[]>> = {
    make_id: ["model_id", "generation_id", "body_variant_id", "modification_id"],
    make_ids: ["model_ids", "generation_id", "body_variant_id", "modification_id"],
    model_ids: ["generation_id", "body_variant_id", "modification_id"],
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
  "modification_id", "body_variant_id", "generation_id", "model_ids", "make_ids", "model_id", "make_id", "engine_volume_max", "engine_volume_min",
  "power_max", "power_min", "fuel", "transmission", "drive", "body_type", "condition", "seller_type", "equipment",
  "color", "customs_status", "technical_condition", "body_condition", "damaged", "parts_only", "district", "call_hours",
  "exchange", "bargaining", "credit", "leasing", "has_vin", "has_photos", "q"
];

export function searchRelaxationOptions(search: ListingSearch, limit = 4) {
  const selected = new Set(activeSearchKeys.filter((key) => {
    const value = search[key];
    return Array.isArray(value) ? value.length > 0 : value !== undefined && value !== null && value !== "";
  }));
  const boundedLimit = Number.isFinite(limit) ? Math.max(0, Math.floor(limit)) : 4;

  return [...new Set([...relaxationPriority, ...activeSearchKeys])]
    .filter((key) => selected.has(key))
    .slice(0, boundedLimit)
    .map((key) => ({
      key,
      href: searchUrl(search, { [key]: undefined } as Partial<ListingSearch>)
    }));
}

export function clearSearchFilters(search: ListingSearch) {
  const patch = Object.fromEntries(activeSearchKeys.map((key) => [key, undefined])) as Partial<ListingSearch>;
  return searchUrl(search, patch);
}
