"use client";

import type { ListingSearch } from "@/lib/types";

export function SearchSort({ search, priceOperationsAvailable = true }: { search: ListingSearch; priceOperationsAvailable?: boolean }) {
  return (
    <form action="/cars" method="get">
      {Object.entries(search).filter(([key, value]) => key !== "sort" && key !== "page" && key !== "currency" && value).flatMap(([key, value]) =>
        Array.isArray(value)
          ? value.map((entry, index) => <input key={`${key}-${entry}-${index}`} type="hidden" name={key} value={entry} />)
          : <input key={key} type="hidden" name={key} value={String(value)} />
      )}
      <input type="hidden" name="currency" value={search.currency || "BYN"} />
      <select
        name="sort"
        aria-label="Сортировка"
        aria-describedby={!priceOperationsAvailable ? "search-sort-price-status" : undefined}
        defaultValue={search.sort || "newest"}
        onChange={(event) => event.currentTarget.form?.requestSubmit()}
      >
        <option value="newest">Сначала новые</option>
        <option value="price_asc" disabled={!priceOperationsAvailable}>Сначала дешевле</option>
        <option value="price_desc" disabled={!priceOperationsAvailable}>Сначала дороже</option>
        <option value="year_desc">Сначала новее по году</option>
        <option value="mileage_asc">Сначала с меньшим пробегом</option>
      </select>
      {!priceOperationsAvailable && (
        <p className="muted" id="search-sort-price-status" role="status">
          Сортировка по цене временно недоступна: нет подтверждённого курса НБРБ за последние 72 часа.
        </p>
      )}
    </form>
  );
}
