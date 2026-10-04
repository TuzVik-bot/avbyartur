import type { ListingSearch } from "@/lib/types";

const allowedSearchKeys: (keyof ListingSearch)[] = [
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
      result[key] = normalized.trim() as never;
    }
  }
  return result;
}

export function searchUrl(search: ListingSearch, patch: Partial<ListingSearch> = {}) {
  const next = { ...search, ...patch };
  const dependencies: Partial<Record<keyof ListingSearch, (keyof ListingSearch)[]>> = {
    make_id: ["model_id", "generation_id", "body_variant_id", "modification_id"],
    model_id: ["generation_id", "body_variant_id", "modification_id"],
    generation_id: ["body_variant_id", "modification_id"],
    region_id: ["city_id"]
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
    if (Array.isArray(value)) {
      for (const entry of value) if (entry) params.append(key, entry);
    } else if (value !== undefined && value !== "") params.set(key, String(value));
  }
  const query = params.toString();
  return query ? `/cars?${query}` : "/cars";
}

export const activeSearchKeys = allowedSearchKeys.filter((key) => !["page", "page_size", "sort", "currency"].includes(key));
