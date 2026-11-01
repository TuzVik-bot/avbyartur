import type { CatalogItem } from "@/lib/types";

function normalizeCatalogText(value: string) {
  return value.normalize("NFD").replace(/\p{M}/gu, "").toLocaleLowerCase();
}

export function matchesCatalogSearch(item: CatalogItem, query: string) {
  const needle = normalizeCatalogText(query.trim());
  return [item.name, ...(item.aliases || [])].some((name) => normalizeCatalogText(name).includes(needle));
}
