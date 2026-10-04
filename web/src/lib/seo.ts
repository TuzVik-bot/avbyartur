import type { Metadata, MetadataRoute } from "next";
import { listingHref } from "@/lib/format";
import { SITE_ORIGIN, siteUrl } from "@/lib/site-config";
import type { CompanySummary, Listing, ListingSummary } from "@/lib/types";

const MAX_SITEMAP_URLS = 50_000;
const MIN_LISTINGS_FOR_MAKE_OR_MODEL_PAGE = 3;
const MIN_LISTINGS_FOR_CITY_PAGE = 10;

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

export function buildListingMetadata(listing: Listing): Metadata {
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
  const canonical = siteUrl(listingHref(listing));

  return {
    title,
    description: details.length ? `${details.join(" · ")} — объявление об автомобиле в Беларуси.`.slice(0, 160) : "Объявление об автомобиле в Беларуси.",
    alternates: { canonical },
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

export function buildSitemapEntries(listings: SitemapListing[], dealers: CompanySummary[]): MetadataRoute.Sitemap {
  const urls = new Set<string>([siteUrl("/"), siteUrl("/cars"), siteUrl("/dealers")]);
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

    if (listing.make?.slug) {
      addListingToAggregate(makeListings, `/cars/${encodeURIComponent(listing.make.slug)}`, listing);
    }
    if (listing.make?.slug && listing.model?.slug) {
      addListingToAggregate(
        modelListings,
        `/cars/${encodeURIComponent(listing.make.slug)}/${encodeURIComponent(listing.model.slug)}`,
        listing,
      );
    }
    if (listing.city?.slug) {
      addListingToAggregate(cityListings, `/cars/city/${encodeURIComponent(listing.city.slug)}`, listing);
    }
    const listingUrl = siteUrl(listingHref(listing));
    urls.add(listingUrl);
    addLastModified(lastModifiedByUrl, listingUrl, listing.updated_at);
  }

  for (const [path, aggregate] of makeListings) {
    if (aggregate.listingIds.size < MIN_LISTINGS_FOR_MAKE_OR_MODEL_PAGE) continue;
    const url = siteUrl(path);
    urls.add(url);
    if (aggregate.lastModified) lastModifiedByUrl.set(url, aggregate.lastModified);
  }
  for (const [path, aggregate] of modelListings) {
    if (aggregate.listingIds.size < MIN_LISTINGS_FOR_MAKE_OR_MODEL_PAGE) continue;
    const url = siteUrl(path);
    urls.add(url);
    if (aggregate.lastModified) lastModifiedByUrl.set(url, aggregate.lastModified);
  }
  for (const [path, aggregate] of cityListings) {
    if (aggregate.listingIds.size < MIN_LISTINGS_FOR_CITY_PAGE) continue;
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
    return lastModified ? { url, lastModified } : { url };
  });
}
