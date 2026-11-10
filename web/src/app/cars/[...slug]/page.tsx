import type { Metadata } from "next";
import { cache, Fragment } from "react";
import { notFound, permanentRedirect } from "next/navigation";
import Link from "next/link";
import { ListingCard } from "@/components/listing-card";
import { ListingDetail } from "@/components/listing-detail";
import { getCatalogCities, SearchRoute } from "@/components/search-route";
import { ApiClientError } from "@/lib/api";
import { getSessionServer, serverApi } from "@/lib/server-api";
import { listingCatalogBreadcrumbs } from "@/lib/listing-breadcrumbs";
import { listingHref, modelDisplayName } from "@/lib/format";
import { ARCHIVED_LISTING_ROBOTS, buildBreadcrumbJsonLd, buildListingMetadata, buildVehicleJsonLd, serializeJsonLd } from "@/lib/seo";
import { siteUrl } from "@/lib/site-config";
import { isCatalogLandingItem, MIN_CATEGORY_LISTINGS, MIN_CITY_LISTINGS } from "@/lib/catalog-indexing";
import type { CatalogCity, CatalogItem, Listing, ListingSearch, ListingSummary } from "@/lib/types";

export const dynamic = "force-dynamic";

const SIMILAR_LISTINGS_LIMIT = 6;

type SimilarListings = { title: string; items: ListingSummary[] };
type CatalogRef = { id: string; name: string } | null | undefined;

const getListing = cache((id: string) => serverApi.listing(id));
const getMakeCatalog = cache((slug: string) => serverApi.catalog("makes", { q: slug, category_code: "cars" }));
const getModelsCatalog = cache((makeId: string) => serverApi.catalog("models", { make_id: makeId, category_code: "cars" }));
const getCityCatalog = cache(getCatalogCities);

const noindexFollowRobots: NonNullable<Metadata["robots"]> = {
  index: false,
  follow: true,
  noarchive: true,
  googleBot: { index: false, follow: true, noimageindex: true },
};

function routeCanonical(slug: string[]) {
  return siteUrl(`/cars/${slug.map(encodeURIComponent).join("/")}`);
}

function categoryMetadata(title: string, slug: string[], total: number | null, minimumListings: number, items: CatalogItem[] = []): Metadata {
  return {
    title,
    alternates: { canonical: routeCanonical(slug) },
    ...(total === null || total < minimumListings || !items.every(isCatalogLandingItem) ? { robots: noindexFollowRobots } : {}),
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
      if (error instanceof ApiClientError && error.status === 410) return { robots: ARCHIVED_LISTING_ROBOTS };
      if (error instanceof ApiClientError && error.status === 404) return {};
      return { alternates: { canonical: routeCanonical(slug) } };
    }
  }

  if (slug[0] === "city" && slug[1]) {
    try {
      const city = (await getCityCatalog()).find((item) => item.slug === slug[1]);
      if (!city) return {};
      const total = await getActiveListingCount({ city_id: city.id });
      return categoryMetadata(`Автомобили в городе ${city.name}`, slug, total, MIN_CITY_LISTINGS, [city]);
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
      return categoryMetadata(`Автомобили ${make.name}`, [make.slug], total, MIN_CATEGORY_LISTINGS, [make]);
    }
    const model = (await getModelsCatalog(make.id)).items.find((item) => item.slug === slug[1]);
    if (!model) return {};
    const total = await getActiveListingCount({ make_id: make.id, model_id: model.id });
    return categoryMetadata(`Купить ${modelDisplayName(make.name, model.name)} в Беларуси`, [make.slug, model.slug], total, MIN_CATEGORY_LISTINGS, [make, model]);
  } catch {
    return categoryMetadata("Автомобили", slug, null, MIN_CATEGORY_LISTINGS);
  }
}

function unavailable(message: string) {
  return <div className="page-width"><p className="notice" role="alert">{message}</p><Link className="button button-secondary" href="/cars">Вернуться к поиску</Link></div>;
}

function gone(similar: SimilarListings | null) {
  return (
    <div className="page-width">
      <p className="notice" role="status">Объявление снято с публикации. Посмотрите другие автомобили в каталоге.</p>
      <Link className="button button-secondary" href="/cars">Вернуться к поиску</Link>
      {similar && similar.items.length > 0 && (
        <section className="related-listings section" aria-labelledby="similar-listings-heading">
          <div className="section-heading"><h2 id="similar-listings-heading">Похожие {similar.title}</h2></div>
          <div className="listing-stack">{similar.items.map((item) => <ListingCard key={item.id} listing={item} variant="row" />)}</div>
        </section>
      )}
    </div>
  );
}

// Similar offers are a courtesy for visitors of a removed listing; any failure just hides the block.
async function similarListings(make: CatalogRef, model: CatalogRef, excludeId?: string): Promise<SimilarListings | null> {
  if (!make || !model) return null;
  try {
    const { items } = await serverApi.listings({ make_id: make.id, model_id: model.id, page_size: String(SIMILAR_LISTINGS_LIMIT) });
    return { title: modelDisplayName(make.name, model.name), items: items.filter((item) => item.id !== excludeId).slice(0, SIMILAR_LISTINGS_LIMIT) };
  } catch {
    return null;
  }
}

// A 410 response carries no listing body, so make and model come from the canonical URL segments.
async function similarListingsForSlug(makeSlug: string, modelSlug: string, excludeId: string): Promise<SimilarListings | null> {
  try {
    const make = (await getMakeCatalog(makeSlug)).items.find((item) => item.slug === makeSlug);
    if (!make) return null;
    const model = (await getModelsCatalog(make.id)).items.find((item) => item.slug === modelSlug);
    return await similarListings(make, model, excludeId);
  } catch {
    return null;
  }
}

async function isListingSaved(listingId: string) {
  if (!await getSessionServer()) return false;
  return (await serverApi.favorites()).items.some((item) => item.id === listingId);
}

// Session and related requests are independent; each one degrades to an empty value on failure.
async function loadListingExtras(listing: Listing) {
  const [saved, related] = await Promise.allSettled([
    isListingSaved(listing.id),
    serverApi.relatedListings(listing.id).then((result) => result.items),
  ]);
  return {
    initialSaved: saved.status === "fulfilled" && saved.value,
    relatedListings: related.status === "fulfilled" ? related.value : [],
  };
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
        if (error.status === 410) return gone(await similarListingsForSlug(slug[0], slug[1], id));
      }
      return unavailable("Не удалось загрузить объявление. Проверьте соединение и повторите попытку.");
    }
    if (listing.status === "archived") return gone(await similarListings(listing.make, listing.model, listing.id));
    if (listing.status !== "active" && listing.status !== "sold") notFound();
    const canonical = listingHref(listing);
    if (canonical !== `/cars/${slug.map(encodeURIComponent).join("/")}`) permanentRedirect(canonical);
    const { initialSaved, relatedListings } = await loadListingExtras(listing);
    const vehicleJsonLd = buildVehicleJsonLd(listing);
    const breadcrumbJsonLd = buildBreadcrumbJsonLd([
      { name: "Главная", path: "/" },
      { name: "Автомобили", path: "/cars" },
      ...listingCatalogBreadcrumbs(listing),
      { name: listing.title || "Объявление", path: listingHref(listing) },
    ]);
    return (
      <Fragment key={listing.id}>
        {vehicleJsonLd && <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: serializeJsonLd(vehicleJsonLd) }} />}
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: serializeJsonLd(breadcrumbJsonLd) }} />
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
    title = `Продажа ${modelDisplayName(make.name, model.name)}`;
  }
  return <div className="page-width"><SearchRoute search={search} title={title} /></div>;
}
