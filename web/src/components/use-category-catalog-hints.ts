import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { CatalogItem } from "@/lib/types";

// Categories whose imported make/model packs back datalist suggestions.
// Cars use the regular catalog selects, so they are intentionally absent.
export const CATEGORY_CATALOG_CODES = [
  "trucks",
  "motorcycles",
  "buses",
  "special_equipment",
  "agricultural_equipment",
  "trailers",
  "watercraft"
] as const;

export function hasCategoryCatalog(category: string) {
  return (CATEGORY_CATALOG_CODES as readonly string[]).includes(category);
}

function matchesMake(item: CatalogItem, typed: string) {
  const needle = typed.trim().toLocaleLowerCase();
  return Boolean(needle) && [item.name, ...(item.aliases || [])].some((name) => name.toLocaleLowerCase() === needle);
}

export function useCategoryCatalogHints(category: string, manualMake: string) {
  const enabled = hasCategoryCatalog(category);
  const [categoryMakes, setCategoryMakes] = useState<CatalogItem[]>([]);
  const [categoryModels, setCategoryModels] = useState<CatalogItem[]>([]);

  useEffect(() => {
    let active = true;
    setCategoryMakes([]);
    if (enabled) {
      api.catalog("makes", { category_code: category })
        .then((result) => { if (active) setCategoryMakes(result.items); })
        .catch(() => { if (active) setCategoryMakes([]); });
    }
    return () => { active = false; };
  }, [category, enabled]);

  useEffect(() => {
    let active = true;
    setCategoryModels([]);
    const make = categoryMakes.find((item) => matchesMake(item, manualMake));
    if (enabled && make) {
      api.catalog("models", { category_code: category, make_id: make.id })
        .then((result) => { if (active) setCategoryModels(result.items); })
        .catch(() => { if (active) setCategoryModels([]); });
    }
    return () => { active = false; };
  }, [category, enabled, categoryMakes, manualMake]);

  return { categoryMakes, categoryModels, hasCategoryCatalog: enabled };
}
