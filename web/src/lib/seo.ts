import type { Metadata, MetadataRoute } from "next";
import { listingHref } from "@/lib/format";
import { DEFAULT_LOCALE } from "@/lib/i18n";
import { SITE_NAME, SITE_ORIGIN, siteUrl } from "@/lib/site-config";
import type { CompanySummary, Listing, ListingSummary } from "@/lib/types";
import type { EditorialArticle } from "@/lib/editorial-articles";
import { isCatalogLandingItem, MIN_CATEGORY_LISTINGS, MIN_CITY_LISTINGS } from "@/lib/catalog-indexing";

const MAX_SITEMAP_URLS = 50_000;

const DEFAULT_OG_IMAGE = { url: "/og-default.jpg", width: 1200, height: 630, alt: SITE_NAME };

// Public pages that belong in the sitemap regardless of catalog content.
export const STATIC_SITEMAP_PATHS = [
  "/makes",
  "/motorcycles",
  "/special-equipment",
  "/agricultural-equipment",
  "/watercraft",
  "/tires-and-wheels",
  "/buses",
  "/trucks",
  "/trailers",
  "/parts",
  "/useful-information",
  "/customs-calculator",
  "/currency-converter",
  "/sale-contract",
  "/vin-check",
  "/services",
  "/about",
  "/faq",
  "/help",
  "/support",
  "/partner",
] as const;

export type SitemapListing = ListingSummary & { status?: Listing["status"] };

type ListingAggregate = { listingIds: Set<string>; lastModified: Date | null };

function parsedLastModified(value: string | null | undefined): Date | null {
  if (!value) return null;
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? new Date(timestamp) : null;
}

function addListingToAggregate(map: Map<string, ListingAggregate>, path: string, listing: SitemapListing) {
  const aggregate = map.get(path) ?? { listingIds: new Set<string>(), lastModified: null };
  aggregate.listingIds.add(listing.id);
  const updatedAt = parsedLastModified(listing.updated_at);
  if (updatedAt && (!aggregate.lastModified || updatedAt > aggregate.lastModified)) {
    aggregate.lastModified = updatedAt;
  }
  map.set(path, aggregate);
}

function addLastModified(map: Map<string, Date>, url: string, updatedAt: string | null | undefined) {
  const date = parsedLastModified(updatedAt);
  const current = map.get(url);
  if (date && (!current || date > current)) map.set(url, date);
}

function validImageUrl(value: string | null | undefined) {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return null;
  try {
    const url = new URL(value, `${SITE_ORIGIN}/`);
    return url.origin === SITE_ORIGIN ? url.toString() : null;
  } catch {
    return null;
  }
}

// A removed listing is a soft-404 for search engines; links to similar offers stay crawlable.
export const ARCHIVED_LISTING_ROBOTS = { index: false, follow: true } as const satisfies NonNullable<Metadata["robots"]>;

export function buildListingMetadata(listing: Listing): Metadata {
  if (listing.status === "archived") return { robots: ARCHIVED_LISTING_ROBOTS };
  if (listing.status !== "active" && listing.status !== "sold") return {};

  const title = listing.title.trim() || [listing.make?.name, listing.model?.name, listing.year]
    .filter((part) => part !== null && part !== undefined && part !== "")
    .join(" ");
  const details = [
    listing.make?.name,
    listing.model?.name,
    listing.year ? `год ${listing.year}` : null,
    listing.mileage_km !== null ? `${new Intl.NumberFormat("ru-BY").format(listing.mileage_km)} км` : null,
    listing.city?.name || listing.manual_city || listing.region?.name,
  ].filter((part): part is string => Boolean(part));
  const description = details.length ? `${details.join(" · ")} — объявление об автомобиле в Беларуси.`.slice(0, 160) : "Объявление об автомобиле в Беларуси.";
  const canonical = siteUrl(listingHref(listing));
  const ogImageCandidates = [...new Set([listing.cover_url, ...(listing.photo_urls || [])])].slice(0, 3);
  const ogImagePaths = ogImageCandidates.filter((value): value is string => Boolean(value && value.startsWith("/") && !value.startsWith("//")));

  return {
    title,
    description,
    alternates: { canonical },
    openGraph: buildOpenGraph({ title, description, path: listingHref(listing), images: ogImagePaths }),
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: ogImagePaths.length ? ogImagePaths : [DEFAULT_OG_IMAGE.url],
    },
    ...(listing.status === "sold" ? {
      robots: {
        index: false,
        follow: false,
        noarchive: true,
        googleBot: { index: false, follow: false, noimageindex: true },
      },
    } : {}),
  };
}

export type OpenGraphInput = {
  title: string;
  description: string;
  path: string;
  images?: string[];
  type?: "website" | "article";
};

export function buildOpenGraph({ title, description, path, images, type = "website" }: OpenGraphInput): NonNullable<Metadata["openGraph"]> {
  const resolvedImages = (images ?? [])
    .map(validImageUrl)
    .filter((url): url is string => url !== null)
    .slice(0, 3)
    .map((url) => ({ url }));
  return {
    type,
    siteName: SITE_NAME,
    locale: DEFAULT_LOCALE,
    url: siteUrl(path),
    title,
    description,
    images: resolvedImages.length ? resolvedImages : [DEFAULT_OG_IMAGE],
  };
}

export function buildVehicleJsonLd(listing: Listing) {
  if (listing.status !== "active") return null;

  const canonical = siteUrl(listingHref(listing));
  const images = [...new Set([listing.cover_url, ...(listing.photo_urls || [])]
    .map(validImageUrl)
    .filter((url): url is string => url !== null))];
  const schema: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "Car",
    name: listing.title,
    url: canonical,
  };

  if (listing.make?.name) schema.brand = { "@type": "Brand", name: listing.make.name };
  if (listing.model?.name) schema.model = listing.model.name;
  if (Number.isInteger(listing.year) && listing.year !== null) schema.vehicleModelDate = String(listing.year);
  if (typeof listing.mileage_km === "number" && Number.isFinite(listing.mileage_km) && listing.mileage_km >= 0) {
    schema.mileageFromOdometer = { "@type": "QuantitativeValue", value: listing.mileage_km, unitCode: "KMT" };
  }
  if (listing.fuel) schema.fuelType = listing.fuel;
  if (listing.transmission) schema.vehicleTransmission = listing.transmission;
  if (listing.drive) schema.driveWheelConfiguration = listing.drive;
  if (listing.body_type) schema.bodyType = listing.body_type;
  if (images.length) schema.image = images;

  const amount = listing.price ? Number(listing.price.amount) : NaN;
  if (listing.price && Number.isFinite(amount) && amount > 0 && ["BYN", "USD"].includes(listing.price.currency)) {
    schema.offers = {
      "@type": "Offer",
      url: canonical,
      price: listing.price.amount,
      priceCurrency: listing.price.currency,
      availability: "https://schema.org/InStock",
    };
  }

  return schema;
}

export function serializeJsonLd(value: unknown) {
  return JSON.stringify(value)
    .replace(/</g, "\\u003c")
    .replace(/\u2028/g, "\\u2028")
    .replace(/\u2029/g, "\\u2029");
}

export function buildWebsiteJsonLd() {
  return {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: SITE_NAME,
    url: siteUrl("/"),
    inLanguage: DEFAULT_LOCALE,
    potentialAction: {
      "@type": "SearchAction",
      target: {
        "@type": "EntryPoint",
        urlTemplate: `${siteUrl("/cars")}?q={search_term_string}`,
      },
      "query-input": "required name=search_term_string",
    },
  };
}

export function buildOrganizationJsonLd() {
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: SITE_NAME,
    url: siteUrl("/"),
    image: siteUrl(DEFAULT_OG_IMAGE.url),
  };
}

export function buildBreadcrumbJsonLd(items: { name: string; path: string }[]) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, index) => {
      const queryIndex = item.path.indexOf("?");
      const pathname = queryIndex < 0 ? item.path : item.path.slice(0, queryIndex);
      const query = queryIndex < 0 ? "" : `?${new URLSearchParams(item.path.slice(queryIndex + 1))}`;
      return {
        "@type": "ListItem",
        position: index + 1,
        name: item.name,
        item: `${siteUrl(pathname)}${query}`,
      };
    }),
  };
}

export function buildArticleJsonLd(article: EditorialArticle, updatedISO: string) {
  const path = `/useful-information/articles/${article.slug}`;
  return {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: article.title,
    description: article.description,
    articleSection: article.section,
    inLanguage: DEFAULT_LOCALE,
    url: siteUrl(path),
    mainEntityOfPage: siteUrl(path),
    datePublished: article.publishedOn ?? updatedISO,
    dateModified: updatedISO,
    author: { "@type": "Organization", name: SITE_NAME, url: siteUrl("/") },
    publisher: { "@type": "Organization", name: SITE_NAME, url: siteUrl("/") },
    image: article.leadImage ? siteUrl(article.leadImage.src) : siteUrl(DEFAULT_OG_IMAGE.url),
  };
}

export function buildDealerJsonLd(dealer: CompanySummary) {
  const schema: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "AutoDealer",
    name: dealer.name,
    url: siteUrl(`/dealers/${encodeURIComponent(dealer.slug)}`),
  };
  if (dealer.address) schema.address = { "@type": "PostalAddress", streetAddress: dealer.address, addressCountry: "BY" };
  if (dealer.logo_url) {
    const logo = validImageUrl(dealer.logo_url);
    if (logo) schema.image = logo;
  }
  return schema;
}

export function buildSitemapEntries(listings: SitemapListing[], dealers: CompanySummary[]): MetadataRoute.Sitemap {
  const urls = new Set<string>([SITE_ORIGIN, siteUrl("/cars"), siteUrl("/dealers"), ...STATIC_SITEMAP_PATHS.map((path) => siteUrl(path))]);
  const listingCompanyIds = new Set<string>();
  const makeListings = new Map<string, ListingAggregate>();
  const modelListings = new Map<string, ListingAggregate>();
  const cityListings = new Map<string, ListingAggregate>();
  const lastModifiedByUrl = new Map<string, Date>();

  for (const listing of listings) {
    // The public listing-search API filters to active, visible ads. Keep the
    // optional status check as a guard if that response ever gains the field.
    if (listing.status && listing.status !== "active") continue;
    if (listing.seller.type === "company") listingCompanyIds.add(listing.seller.id);

    if (isCatalogLandingItem(listing.make) && listing.make) {
      addListingToAggregate(makeListings, `/cars/${encodeURIComponent(listing.make.slug)}`, listing);
    }
    if (isCatalogLandingItem(listing.make) && isCatalogLandingItem(listing.model) && listing.make && listing.model) {
      addListingToAggregate(
        modelListings,
        `/cars/${encodeURIComponent(listing.make.slug)}/${encodeURIComponent(listing.model.slug)}`,
        listing,
      );
    }
    if (isCatalogLandingItem(listing.city) && listing.city) {
      addListingToAggregate(cityListings, `/cars/city/${encodeURIComponent(listing.city.slug)}`, listing);
    }
    const listingUrl = siteUrl(listingHref(listing));
    urls.add(listingUrl);
    addLastModified(lastModifiedByUrl, listingUrl, listing.updated_at);
    addLastModified(lastModifiedByUrl, siteUrl("/cars"), listing.updated_at);
  }

  for (const [path, aggregate] of makeListings) {
    if (aggregate.listingIds.size < MIN_CATEGORY_LISTINGS) continue;
    const url = siteUrl(path);
    urls.add(url);
    if (aggregate.lastModified) lastModifiedByUrl.set(url, aggregate.lastModified);
  }
  for (const [path, aggregate] of modelListings) {
    if (aggregate.listingIds.size < MIN_CATEGORY_LISTINGS) continue;
    const url = siteUrl(path);
    urls.add(url);
    if (aggregate.lastModified) lastModifiedByUrl.set(url, aggregate.lastModified);
  }
  for (const [path, aggregate] of cityListings) {
    if (aggregate.listingIds.size < MIN_CITY_LISTINGS) continue;
    const url = siteUrl(path);
    urls.add(url);
    if (aggregate.lastModified) lastModifiedByUrl.set(url, aggregate.lastModified);
  }

  for (const dealer of dealers) {
    if (dealer.status === "approved" && listingCompanyIds.has(dealer.id) && dealer.slug) {
      urls.add(siteUrl(`/dealers/${encodeURIComponent(dealer.slug)}`));
    }
  }

  return [...urls].slice(0, MAX_SITEMAP_URLS).map((url) => {
    const lastModified = lastModifiedByUrl.get(url);
    const changeFrequency = new URL(url).pathname.startsWith("/cars") ? "daily" as const : undefined;
    return { url, ...(lastModified ? { lastModified } : {}), ...(changeFrequency ? { changeFrequency } : {}) };
  });
}
