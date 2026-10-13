import { redirect } from "next/navigation";
import { ApiClientError } from "@/lib/api";
import { SearchResults } from "@/components/search-results";
import { getSavedListingIds, serverApi } from "@/lib/server-api";
import { searchUrl } from "@/lib/search-state";
import type { CatalogCity, CatalogItem, CatalogModification, ListingSearch, ListingSearchResponse } from "@/lib/types";
export async function getCatalogCities(regionsPromise?: Promise<CatalogItem[]>): Promise<CatalogCity[]> {
  const regions = regionsPromise || serverApi.regions().then((result) => result.items);
  const cityGroups = await Promise.all((await regions).map(async (region) => {
    const result = await serverApi.cities(region.id);
    return result.items.map((city) => ({ ...city, region_id: region.id }));
  }));
  return cityGroups.flat();
}

export async function SearchRoute({ search, title, initialCities }: { search: ListingSearch; title: string; initialCities?: CatalogCity[] }) {
  const isCars = !search.category_code || search.category_code === "cars";
  const regionsPromise = serverApi.regions();
  const citiesPromise = initialCities
    ? Promise.resolve({ items: initialCities })
    : search.region_id
      ? serverApi.cities(search.region_id).then((result) => ({
        items: result.items.map((city) => ({ ...city, region_id: search.region_id! }))
      }))
      : search.city_id
        ? getCatalogCities(regionsPromise.then((result) => result.items)).then((items) => ({ items }))
        : Promise.resolve({ items: [] as CatalogCity[] });
  const [listingsResult, makesResult, modelsResult, generationsResult, regionsResult, citiesResult, bodyTypesResult, bodyVariantsResult, modificationsResult, savedListingIdsResult] = await Promise.allSettled([
    serverApi.listings({ ...search, page_size: search.page_size || "25" }),
    isCars ? serverApi.catalog("makes") : Promise.resolve({ items: [] as CatalogItem[] }),
    search.make_id ? serverApi.catalog("models", { make_id: search.make_id }) : Promise.resolve({ items: [] as CatalogItem[] }),
    search.model_id ? serverApi.catalog("generations", { model_id: search.model_id }) : Promise.resolve({ items: [] as CatalogItem[] }),
    regionsPromise,
    citiesPromise,
    isCars ? serverApi.catalog("body-types") : Promise.resolve({ items: [] as CatalogItem[] }),
    search.generation_id && search.body_variant_id
      ? serverApi.catalog("body-variants", { generation_id: search.generation_id })
      : Promise.resolve({ items: [] as CatalogItem[] }),
    search.generation_id
      ? serverApi.catalog("modifications", { generation_id: search.generation_id })
      : Promise.resolve({ items: [] as CatalogModification[] }),
    getSavedListingIds()
  ]);
  const data: ListingSearchResponse | null = listingsResult.status === "fulfilled" ? listingsResult.value : null;
  const priceSortRequested = search.sort === "price_asc" || search.sort === "price_desc";
  const priceFilterRequested = Boolean(search.price_min || search.price_max);
  const failure = listingsResult.status === "rejected" ? listingsResult.reason : null;
  if (failure instanceof ApiClientError && failure.code === "exchange_rate_unavailable" && (priceFilterRequested || priceSortRequested)) {
    redirect(searchUrl(search, {
      price_min: undefined,
      price_max: undefined,
      sort: priceSortRequested ? undefined : search.sort,
      page: undefined
    }));
  }
  const makes = makesResult.status === "fulfilled" ? makesResult.value.items : [];
  const models = modelsResult.status === "fulfilled" ? modelsResult.value.items : [];
  const generations = generationsResult.status === "fulfilled" ? generationsResult.value.items : undefined;
  const regions = regionsResult.status === "fulfilled" ? regionsResult.value.items : [];
  const cities = citiesResult.status === "fulfilled" ? citiesResult.value.items : [];
  const bodyTypes = bodyTypesResult.status === "fulfilled" ? bodyTypesResult.value.items : [];
  const bodyVariants = bodyVariantsResult.status === "fulfilled" ? bodyVariantsResult.value.items : [];
  const modifications = modificationsResult.status === "fulfilled" ? modificationsResult.value.items : [];
  const savedListingIds = savedListingIdsResult.status === "fulfilled" ? savedListingIdsResult.value : [];
  const catalogsFailed = [makesResult, modelsResult, generationsResult, regionsResult, citiesResult, bodyTypesResult, bodyVariantsResult, modificationsResult].some((result) => result.status === "rejected");

  return <div className="page-width"><SearchResults search={search} data={data} title={title} makes={makes} models={models} generations={generations} regions={regions} cities={cities} bodyTypes={bodyTypes} bodyVariants={bodyVariants} modifications={modifications} savedListingIds={savedListingIds} failed={listingsResult.status === "rejected"} catalogsFailed={catalogsFailed} priceOperationsAvailable={data ? Boolean(data.fx) : true} /></div>;
}
