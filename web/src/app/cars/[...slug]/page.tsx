import type { Metadata } from "next";
import { cache, Fragment } from "react";
import { notFound, redirect } from "next/navigation";
import Link from "next/link";
import { ListingDetail } from "@/components/listing-detail";
import { getCatalogCities, SearchRoute } from "@/components/search-route";
import { ApiClientError } from "@/lib/api";
import { getSessionServer, serverApi } from "@/lib/server-api";
import { listingHref } from "@/lib/format";
import { buildListingMetadata, buildVehicleJsonLd, serializeJsonLd } from "@/lib/seo";
import { siteUrl } from "@/lib/site-config";
import type { CatalogCity, CatalogItem, ListingSearch } from "@/lib/types";

export const dynamic = "force-dynamic";

const getListing = cache((id: string) => serverApi.listing(id));
const getMakeCatalog = cache((slug: string) => serverApi.catalog("makes", { q: slug }));
const getModelsCatalog = cache((makeId: string) => serverApi.catalog("models", { make_id: makeId }));
const getCityCatalog = cache(getCatalogCities);
const MIN_CATEGORY_LISTINGS = 3;
const MIN_CITY_LISTINGS = 10;

const noindexFollowRobots: NonNullable<Metadata["robots"]> = {
  index: false,
  follow: true,
  noarchive: true,
  googleBot: { index: false, follow: true, noimageindex: true },
};

function routeCanonical(slug: string[]) {
  return siteUrl(`/cars/${slug.map(encodeURIComponent).join("/")}`);
}

function categoryMetadata(title: string, slug: string[], total: number | null, minimumListings: number): Metadata {
  return {
    title,
    alternates: { canonical: routeCanonical(slug) },
    ...(total === null || total < minimumListings ? { robots: noindexFollowRobots } : {}),
  };
}

async function getActiveListingCount(search: ListingSearch): Promise<number | null> {
  try {
    const response = await serverApi.listings({ ...search, page_size: "1" });
    const total = response.pagination?.total;
    return typeof total === "number" && Number.isSafeInteger(total) && total >= 0 ? total : null;
  } catch {
    return null;
  }
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string[] }> }): Promise<Metadata> {
  const { slug } = await params;
  if (slug.length >= 3) {
    const id = slug[slug.length - 1];
    try {
      const { listing } = await getListing(id);
      return buildListingMetadata(listing);
    } catch (error) {
      if (error instanceof ApiClientError && (error.status === 404 || error.status === 410)) return {};
      return { alternates: { canonical: routeCanonical(slug) } };
    }
  }

  if (slug[0] === "city" && slug[1]) {
    try {
      const city = (await getCityCatalog()).find((item) => item.slug === slug[1]);
      if (!city) return {};
      const total = await getActiveListingCount({ city_id: city.id });
      return categoryMetadata(`Автомобили в городе ${city.name}`, slug, total, MIN_CITY_LISTINGS);
    } catch {
      return categoryMetadata("Автомобили в городе", slug, null, MIN_CITY_LISTINGS);
    }
  }

  const makeSlug = slug[0];
  if (!makeSlug || slug.length > 2) return {};
  try {
    const make = (await getMakeCatalog(makeSlug)).items.find((item) => item.slug === makeSlug);
    if (!make) return {};
    if (!slug[1]) {
      const total = await getActiveListingCount({ make_id: make.id });
      return categoryMetadata(`Автомобили ${make.name}`, [make.slug], total, MIN_CATEGORY_LISTINGS);
    }
    const model = (await getModelsCatalog(make.id)).items.find((item) => item.slug === slug[1]);
    if (!model) return {};
    const total = await getActiveListingCount({ make_id: make.id, model_id: model.id });
    return categoryMetadata(`${make.name} ${model.name}`, [make.slug, model.slug], total, MIN_CATEGORY_LISTINGS);
  } catch {
    return categoryMetadata("Автомобили", slug, null, MIN_CATEGORY_LISTINGS);
  }
}

function unavailable(message: string) {
  return <div className="page-width"><p className="notice" role="alert">{message}</p><Link className="button button-secondary" href="/cars">Вернуться к поиску</Link></div>;
}

function gone() {
  return <div className="page-width"><p className="notice" role="status">Объявление снято с публикации. Посмотрите другие автомобили в каталоге.</p><Link className="button button-secondary" href="/cars">Вернуться к поиску</Link></div>;
}

export default async function CarsBySlugPage({ params }: { params: Promise<{ slug: string[] }> }) {
  const { slug } = await params;
  if (slug.length >= 3) {
    const id = slug[slug.length - 1];
    let listing;
    try {
      listing = (await getListing(id)).listing;
    } catch (error) {
      if (error instanceof ApiClientError) {
        if (error.status === 404) notFound();
        if (error.status === 410) return gone();
      }
      return unavailable("Не удалось загрузить объявление. Проверьте соединение и повторите попытку.");
    }
    if (listing.status === "archived") return gone();
    if (listing.status !== "active" && listing.status !== "sold") notFound();
    const canonical = listingHref(listing);
    if (canonical !== `/cars/${slug.map(encodeURIComponent).join("/")}`) redirect(canonical);
    let initialSaved = false;
    try {
      if (await getSessionServer()) {
        initialSaved = (await serverApi.favorites()).items.some((item) => item.id === listing.id);
      }
    } catch { /* Keep the public detail page available if session or favorites are temporarily unavailable. */ }
    let relatedListings: import("@/lib/types").ListingSummary[] = [];
    try { relatedListings = (await serverApi.relatedListings(listing.id)).items; }
    catch { /* A related-listing outage does not block the primary detail page. */ }
    const vehicleJsonLd = buildVehicleJsonLd(listing);
    return (
      <Fragment key={listing.id}>
        {vehicleJsonLd && <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: serializeJsonLd(vehicleJsonLd) }} />}
        <ListingDetail listing={listing} initialSaved={initialSaved} relatedListings={relatedListings} />
      </Fragment>
    );
  }

  if (slug[0] === "city" && slug[1]) {
    let cities: CatalogCity[] = [];
    try { cities = await getCityCatalog(); } catch {
      return unavailable("Справочник населённых пунктов временно недоступен. Повторите попытку позже.");
    }
    const city = cities.find((item) => item.slug === slug[1]);
    if (!city) notFound();
    const search: ListingSearch = { city_id: city.id, page_size: "25" };
    return <div className="page-width"><SearchRoute search={search} initialCities={cities} title={`Автомобили в городе ${city.name}`} /></div>;
  }

  const makeSlug = slug[0];
  if (!makeSlug) notFound();
  let makes: CatalogItem[] = [];
  try { makes = (await getMakeCatalog(makeSlug)).items; } catch {
    return unavailable("Справочник марок временно недоступен. Повторите попытку позже.");
  }
  const make = makes.find((item) => item.slug === makeSlug);
  if (!make) notFound();

  let search: ListingSearch = { make_id: make.id, page_size: "25" };
  let title = `Автомобили ${make.name}`;
  if (slug[1]) {
    let models: CatalogItem[] = [];
    try { models = (await getModelsCatalog(make.id)).items; } catch {
      return unavailable("Список моделей временно недоступен. Повторите попытку позже.");
    }
    const model = models.find((item) => item.slug === slug[1]);
    if (!model) notFound();
    search = { make_id: make.id, model_id: model.id, page_size: "25" };
    title = `${make.name} ${model.name}`;
  }
  return <div className="page-width"><SearchRoute search={search} title={title} /></div>;
}
