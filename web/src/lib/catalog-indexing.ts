import type { CatalogItem } from "@/lib/types";

export const MIN_CATEGORY_LISTINGS = 3;
export const MIN_CITY_LISTINGS = 10;

// manual-* represents a listing's free-text fallback, not a catalog route.
// cur-unicode-* is a real catalog slug for Cyrillic names such as ГАЗ.
export function isCatalogLandingItem(item: Pick<CatalogItem, "slug" | "name"> | null | undefined): boolean {
  return Boolean(item?.slug && item.name?.trim() && !item.slug.startsWith("manual-"));
}
