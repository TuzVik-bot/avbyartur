import type { Listing } from "./types";

/** Snapshot/manual catalog labels have synthetic slugs with no category page. */
export function listingCatalogBreadcrumbs({ make, model }: Pick<Listing, "make" | "model">) {
  if (!make) return [];
  const manualMake = make.slug.startsWith("manual-");
  const makePath = manualMake
    ? `/cars?${new URLSearchParams({ q: make.name })}`
    : `/cars/${encodeURIComponent(make.slug)}`;
  const items = [{ name: make.name, path: makePath }];
  if (model) {
    const path = manualMake || model.slug.startsWith("manual-")
      ? `/cars?${new URLSearchParams(manualMake ? { q: `${make.name} ${model.name}` } : { make_id: make.id, q: model.name })}`
      : `${makePath}/${encodeURIComponent(model.slug)}`;
    items.push({ name: model.name, path });
  }
  return items;
}
