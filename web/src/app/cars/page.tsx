import type { Metadata } from "next";
import { SearchRoute } from "@/components/search-route";
import { readSearchParams, searchUrl } from "@/lib/search-state";
import { SITE_ORIGIN } from "@/lib/site-config";
import type { ListingCategoryCode } from "@/lib/listing-subcategories";

type SearchParamsRecord = Record<string, string | string[] | undefined>;
const categoryTitles: Record<ListingCategoryCode, string> = {
  cars: "Автомобили Беларуси",
  trucks: "Грузовые автомобили Беларуси",
  buses: "Автобусы Беларуси",
  motorcycles: "Мотоциклы и ATV Беларуси",
  special_equipment: "Спецтехника Беларуси",
  agricultural_equipment: "Сельхозтехника Беларуси",
  trailers: "Прицепы Беларуси",
  watercraft: "Водный транспорт Беларуси",
  parts: "Автозапчасти Беларуси",
  wheels: "Колёсные диски Беларуси",
  tires: "Шины Беларуси",
};

function titleForCategory(categoryCode?: ListingCategoryCode) {
  return categoryTitles[categoryCode || "cars"];
}

export async function generateMetadata({ searchParams }: { searchParams: Promise<SearchParamsRecord> }): Promise<Metadata> {
  const params = await searchParams;
  const search = readSearchParams(params);
  if (search.page === "1") delete search.page;
  const hasQueryVariant = Object.entries(params).some(([key, value]) => {
    if (value === undefined) return false;
    const values = Array.isArray(value) ? value : [value];
    return values.some((entry) => key !== "page" || entry !== "1");
  });
  const canonical = new URL(searchUrl(search), `${SITE_ORIGIN}/`).toString();
  return {
    title: `Найти: ${titleForCategory(search.category_code)}`,
    alternates: { canonical },
    ...(hasQueryVariant ? { robots: { index: false, follow: true, googleBot: { index: false, follow: true } } } : {}),
  };
}

export default async function CarsPage({ searchParams }: { searchParams: Promise<SearchParamsRecord> }) {
  const search = readSearchParams(await searchParams);
  return <SearchRoute search={search} title={titleForCategory(search.category_code)} />;
}
