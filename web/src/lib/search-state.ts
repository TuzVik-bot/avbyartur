import type { ListingSearch } from "@/lib/types";

const categoryCodes: readonly NonNullable<ListingSearch["category_code"]>[] = [
  "cars", "trucks", "buses", "motorcycles", "special_equipment", "agricultural_equipment", "trailers", "watercraft", "parts", "wheels", "tires"
];
const categoryCodeSet: ReadonlySet<string> = new Set(categoryCodes);

function isCategoryCode(value: unknown): value is NonNullable<ListingSearch["category_code"]> {
  return typeof value === "string" && categoryCodeSet.has(value);
}

const allowedSearchKeys: (keyof ListingSearch)[] = [
  "category_code", "subtype", "details", "diameter_in", "width_mm", "season",
  "q", "make_id", "model_id", "generation_id", "body_variant_id", "modification_id", "price_min", "price_max", "currency", "year_min", "year_max",
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
      result[key] = trimmed as never;
    }
  }
  return result;
}

export function searchUrl(search: ListingSearch, patch: Partial<ListingSearch> = {}) {
  const next = { ...search, ...patch };
  const category = next.category_code ?? "cars";
  const categories = new Set(["cars", "trucks", "buses", "motorcycles", "special_equipment", "agricultural_equipment", "trailers", "watercraft", "parts", "wheels", "tires"]);
  if (!categories.has(category)) throw new Error("Unsupported listing category");
  const dependencies: Partial<Record<keyof ListingSearch, (keyof ListingSearch)[]>> = {
    make_id: ["model_id", "generation_id", "body_variant_id", "modification_id"],
    model_id: ["generation_id", "body_variant_id", "modification_id"],
    generation_id: ["body_variant_id", "modification_id"],
    region_id: ["city_id"]
  };
  if (Object.hasOwn(patch, "category_code") && patch.category_code !== search.category_code) {
    for (const key of ["subtype", "details", "diameter_in", "width_mm", "season", "make_id", "model_id", "generation_id", "body_variant_id", "modification_id"] as (keyof ListingSearch)[]) {
      if (!Object.hasOwn(patch, key)) next[key] = undefined;
    }
  }
  if (category !== "cars") next.category_code = category;
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
    if (Array.isArray(value)) {
      for (const entry of value) if (entry) params.append(key, entry);
    } else if (value !== undefined && value !== "") params.set(key, String(value));
  }
  const query = params.toString();
  const path = `/${category.replaceAll("_", "-")}`;
  return query ? `${path}?${query}` : path;
}

export const activeSearchKeys = allowedSearchKeys.filter((key) => !["category_code", "page", "page_size", "sort", "currency"].includes(key));
