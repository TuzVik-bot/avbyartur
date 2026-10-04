import { categorySearch } from "@/lib/listing-categories";
import type { Metadata } from "next";
import { SearchRoute } from "@/components/search-route";
import { readSearchParams, searchUrl } from "@/lib/search-state";
import { SITE_ORIGIN } from "@/lib/site-config";

type SearchParamsRecord = Record<string, string | string[] | undefined>;

export async function generateMetadata({ searchParams }: { searchParams: Promise<SearchParamsRecord> }): Promise<Metadata> {
  const search = categorySearch("cars", readSearchParams(await searchParams));
  const canonical = new URL(searchUrl({ ...search, category_code: undefined }), `${SITE_ORIGIN}/`).toString();
  return { title: "Найти автомобиль", alternates: { canonical } };
}

export default async function CarsPage({ searchParams }: { searchParams: Promise<SearchParamsRecord> }) {
  const search = categorySearch("cars", readSearchParams(await searchParams));
  return <SearchRoute search={search} title="Автомобили Беларуси" />;
}
