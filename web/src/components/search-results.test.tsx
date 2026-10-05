import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SearchResults } from "@/components/search-results";
import type { CatalogItem, CatalogModification, ListingSearch, ListingSummary } from "@/lib/types";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a>
}));
vi.mock("@/components/listing-card", () => ({
  ListingCard: ({ listing, saved = false }: { listing: ListingSummary; saved?: boolean }) => <div data-listing-id={listing.id} data-favorite-saved={String(saved)} />
}));
vi.mock("@/components/search-filters", () => ({
  SearchFilters: ({ priceOperationsAvailable }: { priceOperationsAvailable: boolean }) => <div data-price-operations-available={String(priceOperationsAvailable)} />
}));

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

const listing: ListingSummary = {
  id: "listing-1",
  slug: "listing-1",
  title: "Марка Модель",
  make: { id: "make-1", slug: "marka", name: "Марка" },
  model: { id: "model-1", slug: "model", name: "Модель" },
  year: 2020,
  mileage_km: 50000,
  fuel: "petrol",
  transmission: "manual",
  drive: "front",
  price: { amount: "10000", currency: "BYN" },
  region: { id: "region-1", slug: "region", name: "Область" },
  city: { id: "city-1", slug: "minsk", name: "Минск" },
  seller: { id: "seller-1", type: "private", name: "Продавец" },
  created_at: "2026-09-27T00:00:00Z",
  updated_at: "2026-09-27T00:00:00Z",
  damaged: false,
  parts_only: false
};

async function render(search: ListingSearch, catalogsFailed = false, savedListingIds: string[] = [], items: ListingSummary[] = [], priceOperationsAvailable = true, modifications: CatalogModification[] = [], generations: CatalogItem[] = [], bodyVariants: CatalogItem[] = []) {
  await act(async () => root.render(createElement(SearchResults, {
    search,
    data: { items, pagination: { page: 1, page_size: 25, total: items.length, pages: items.length ? 1 : 0 } },
    title: "Объявления",
    makes: [], models: [], regions: [], cities: [], bodyTypes: [], modifications, generations, bodyVariants, catalogsFailed,
    savedListingIds, priceOperationsAvailable
  })));
}

describe("search result controls", () => {
  it("submits BYN with sorting on a fresh cars URL", async () => {
    await render({});

    const sortForm = container.querySelector<HTMLFormElement>(".results-toolbar form");
    expect(sortForm?.querySelector<HTMLSelectElement>('select[name="sort"]')?.value).toBe("newest");
    expect(sortForm?.querySelector<HTMLInputElement>('input[name="currency"]')?.value).toBe("BYN");
  });

  it("does not render a removable currency chip", async () => {
    await render({ currency: "BYN" });

    expect(container.querySelector('[aria-label="Выбранные фильтры"]')).toBeNull();
    expect(container.querySelectorAll('.results-toolbar input[name="currency"]')).toHaveLength(1);
  });

  it("shows the selected modification by catalog name and keeps a human-readable fallback", async () => {
    const modification: CatalogModification = { id: "mod-1", slug: "318i", name: "318i", generation_id: "generation-1", specs: null };
    await render({ generation_id: "generation-1", modification_id: modification.id }, false, [], [], true, [modification]);

    const chip = [...container.querySelectorAll<HTMLAnchorElement>(".filter-chip")]
      .find((link) => link.textContent?.includes("Модификация"));
    expect(chip?.textContent).toContain("Модификация: 318i");
    expect(chip?.getAttribute("href")).toBe("/cars?generation_id=generation-1");

    await render({ modification_id: "unresolved-catalog-id" });
    const fallbackChip = [...container.querySelectorAll<HTMLAnchorElement>(".filter-chip")]
      .find((link) => link.textContent?.includes("Модификация"));
    expect(fallbackChip?.textContent).toContain("Модификация: Комплектация выбрана");
    expect(fallbackChip?.textContent).not.toContain("unresolved-catalog-id");
  });

  it("shows a readable fallback chip for a selected body variant", async () => {
    const variant: CatalogItem = { id: "variant-1", slug: "sedan", name: "Седан", generation_id: "generation-1" };
    await render({ generation_id: "generation-1", body_variant_id: variant.id }, false, [], [], true, [], [], [variant]);

    const chip = [...container.querySelectorAll<HTMLAnchorElement>(".filter-chip")]
      .find((link) => link.textContent?.includes("Вариант кузова"));
    expect(chip?.textContent).toContain("Вариант кузова: Седан");
    expect(chip?.getAttribute("href")).toBe("/cars?generation_id=generation-1");

    await render({ generation_id: "generation-1", body_variant_id: "unresolved-catalog-id" });
    const fallbackChip = [...container.querySelectorAll<HTMLAnchorElement>(".filter-chip")]
      .find((link) => link.textContent?.includes("Вариант кузова"));
    expect(fallbackChip?.textContent).toContain("Вариант кузова: Вариант кузова выбран");
    expect(fallbackChip?.textContent).not.toContain("unresolved-catalog-id");
  });

  it("shows the selected generation by catalog name and avoids exposing unresolved IDs", async () => {
    const generation: CatalogItem = { id: "generation-1", slug: "m5-f90", name: "M5 F90", model_id: "model-1" };
    await render({ generation_id: generation.id }, false, [], [], true, [], [generation]);

    const chip = [...container.querySelectorAll<HTMLAnchorElement>(".filter-chip")]
      .find((link) => link.textContent?.includes("Поколение"));
    expect(chip?.textContent).toContain("Поколение: M5 F90");

    await render({ generation_id: "unresolved-generation-id" });
    const fallbackChip = [...container.querySelectorAll<HTMLAnchorElement>(".filter-chip")]
      .find((link) => link.textContent?.includes("Поколение"));
    expect(fallbackChip?.textContent).toContain("Поколение: Поколение выбрано");
    expect(fallbackChip?.textContent).not.toContain("unresolved-generation-id");
  });

  it("explains when filter catalogs failed while keeping results usable", async () => {
    await render({}, true);

    expect(container.querySelector('[role="status"]')?.textContent).toContain("справочников фильтров временно недоступна");
    expect(container.querySelector('a[href="/cars"]')).not.toBeNull();
  });

  it("marks saved search results as favorites", async () => {
    await render({}, false, [listing.id], [listing]);

    expect(container.querySelector('[data-listing-id="listing-1"]')?.getAttribute("data-favorite-saved")).toBe("true");
  });

  it("offers a seller path when the catalogue has no results and no filters are active", async () => {
    await render({});

    const sellCta = container.querySelector('.empty-state a[href="/sell"]');
    expect(sellCta).not.toBeNull();
    expect(sellCta?.textContent).toContain("Подать объявление");
    expect(container.querySelector('.empty-state a[href="/cars"]')).toBeNull();
  });

  it("offers a filter reset for a query with no matches", async () => {
    await render({ make_id: "make-1", price_max: "10000" });

    expect(container.querySelector('.empty-state a[href="/cars"]')?.textContent).toContain("Сбросить фильтры");
    expect(container.querySelector('a[href="/sell"]')).toBeNull();
  });

  it("explains stale currency data and passes disabled price controls", async () => {
    await render({}, false, [], [], false);

    expect(container.querySelector('[role="status"]')?.textContent).toContain("нет подтверждённого курса НБРБ за последние 72 часа");
    expect(container.querySelector("[data-price-operations-available]")?.getAttribute("data-price-operations-available")).toBe("false");
    expect(container.querySelector<HTMLOptionElement>('option[value="price_asc"]')?.disabled).toBe(true);
  });
});
it("keeps resets and submission in the empty category", async () => {
 await render({ category_code: "trucks", q: "MAN" });
 expect(container.querySelector('a[href="/trucks"]')).not.toBeNull();
 expect(container.querySelector('a[href="/sell?category=trucks"]')).not.toBeNull();
 expect(container.querySelector('.filter-chip[href="/cars"]')).toBeNull();
});
it("labels goods search characteristics for people rather than JSON", async () => {
 await render({ category_code: "tires", details: '{"diameter_in":16,"season":"winter"}' });
 const chips = container.querySelector('.active-filters')?.textContent;
 expect(chips).toContain('Диаметр, дюймы: 16');
 expect(chips).toContain('Сезон: Зимние');
 expect(chips).not.toContain('"season"');
});
