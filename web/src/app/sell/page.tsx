import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { SellForm } from "@/components/sell-form";
import { ApiClientError } from "@/lib/api";
import { serverApi } from "@/lib/server-api";
import { requireSession } from "@/lib/server";
import type { CatalogItem, Company, Listing, ListingPhoto } from "@/lib/types";

type SearchParams = { listing?: string | string[] };
export const metadata: Metadata = { title: "Подать объявление" };

export default async function SellPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  await requireSession("/sell");
  const params = await searchParams;
  const id = Array.isArray(params.listing) ? params.listing[0] : params.listing;
  const [makesResult, regionsResult, typesResult, companyResult, listingResult] = await Promise.allSettled([
    serverApi.catalog("makes"),
    serverApi.regions(),
    serverApi.catalog("body-types"),
    serverApi.company(),
    id ? serverApi.listing(id) : Promise.resolve({ listing: null as Listing | null })
  ]);
  const makes: CatalogItem[] = makesResult.status === "fulfilled" ? makesResult.value.items : [];
  const regions: CatalogItem[] = regionsResult.status === "fulfilled" ? regionsResult.value.items : [];
  const bodyTypes: CatalogItem[] = typesResult.status === "fulfilled" ? typesResult.value.items : [];
  const company: Company | null = companyResult.status === "fulfilled" ? companyResult.value.company : null;
  const initialListing = id && listingResult.status === "fulfilled" ? listingResult.value.listing : null;
  if (id && listingResult.status === "rejected") {
    const status = listingResult.reason instanceof ApiClientError ? listingResult.reason.status : undefined;
    if (status === 404 || status === 410) notFound();
    return <div className="page-width"><p className="notice" role="alert">Не удалось загрузить объявление для редактирования. Повторите попытку позже.</p><Link className="button button-secondary" href={`/sell?listing=${encodeURIComponent(id)}`}>Повторить загрузку</Link></div>;
  }
  if (id && (!initialListing || ["sold", "archived", "blocked"].includes(initialListing.status))) notFound();
  const makeId = initialListing?.make?.id;
  const modelId = initialListing?.model?.id;
  const regionId = initialListing?.region?.id;
  const [modelsResult, generationsResult, citiesResult, photosResult] = await Promise.allSettled([
    makeId ? serverApi.catalog("models", { make_id: makeId }) : Promise.resolve({ items: [] as CatalogItem[] }),
    modelId ? serverApi.catalog("generations", { model_id: modelId }) : Promise.resolve({ items: [] as CatalogItem[] }),
    regionId ? serverApi.cities(regionId) : Promise.resolve({ items: [] as CatalogItem[] }),
    id ? serverApi.photos(id) : Promise.resolve({ items: [] as ListingPhoto[] })
  ]);
  const models = modelsResult.status === "fulfilled" ? modelsResult.value.items : initialListing?.model ? [initialListing.model] : [];
  const generations = generationsResult.status === "fulfilled" ? generationsResult.value.items : initialListing?.generation ? [initialListing.generation] : [];
  const cities = citiesResult.status === "fulfilled" ? citiesResult.value.items : initialListing?.city ? [initialListing.city] : [];
  if (id && photosResult.status === "rejected") return <div className="page-width"><p className="notice" role="alert">Не удалось загрузить фотографии объявления. Чтобы не потерять их при редактировании, повторите попытку позже.</p><Link className="button button-secondary" href={`/sell?listing=${encodeURIComponent(id)}`}>Повторить загрузку</Link></div>;
  const listingWithPhotos = initialListing && photosResult.status === "fulfilled" ? { ...initialListing, photos: photosResult.value.items } : initialListing;
  const makeCatalogUnavailable = makesResult.status === "rejected" || !makes.length;
  const regionCatalogUnavailable = regionsResult.status === "rejected" || !regions.length;
  const retryHref = id ? `/sell?listing=${encodeURIComponent(id)}` : "/sell";
  return (
    <div className="page-width">
      {makeCatalogUnavailable && <p className="notice" role="status">Справочник марок недоступен. Марку можно указать вручную в форме. <Link href={retryHref}>Повторить загрузку</Link></p>}
      {regionCatalogUnavailable && <p className="notice" role="alert">Справочник областей недоступен. Объявление можно сохранить как черновик, но отправить его на проверку получится после загрузки справочника. <Link href={retryHref}>Повторить загрузку</Link></p>}
      {companyResult.status === "rejected" && <p className="notice" role="status">Не удалось загрузить профиль компании. Сейчас доступна подача от частного лица.</p>}
      {initialListing && (modelsResult.status === "rejected" || generationsResult.status === "rejected" || citiesResult.status === "rejected") && <p className="notice" role="status">Не удалось загрузить часть справочников редактирования. Текущие значения сохранены; повторите загрузку перед изменением каталожных данных.</p>}
      <SellForm initialListing={listingWithPhotos} makes={makes} models={models} generations={generations} bodyTypes={bodyTypes} regions={regions} cities={cities} company={company} />
    </div>
  );
}
