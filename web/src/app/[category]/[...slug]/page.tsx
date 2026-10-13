import type { Metadata } from "next";
import { cache, Fragment } from "react";
import { notFound, redirect } from "next/navigation";
import Link from "next/link";
import { ListingDetail } from "@/components/listing-detail";
import { categories, categoryPath, type CategoryCode } from "@/lib/listing-categories";
import { ApiClientError } from "@/lib/api";
import { getSessionServer, serverApi } from "@/lib/server-api";
import { listingHref } from "@/lib/format";
import { buildListingMetadata, buildVehicleJsonLd, serializeJsonLd } from "@/lib/seo";
import { siteUrl } from "@/lib/site-config";
import type { Listing } from "@/lib/types";

export const dynamic = "force-dynamic";

const categoryByPath = new Map<string, CategoryCode>(
  categories.filter(({ code }) => code !== "cars").map(({ code }) => [categoryPath(code).slice(1), code]),
);
const getListing = cache((id: string) => serverApi.listing(id));

type RouteParams = { category: string; slug: string[] };

function requestedCategory(value: string) {
  return categoryByPath.get(value) || null;
}

function routePath({ category, slug }: RouteParams) {
  return `/${category}/${slug.map(encodeURIComponent).join("/")}`;
}

function unavailable(categoryCode: CategoryCode) {
  const href = categoryPath(categoryCode);
  const categoryName = categories.find((item) => item.code === categoryCode)?.label || "разделу";
  return <div className="page-width"><p className="notice" role="alert">Не удалось загрузить объявление. Проверьте соединение и повторите попытку.</p><Link className="button button-secondary" href={href}>Вернуться в раздел «{categoryName}»</Link></div>;
}

function gone(categoryCode: CategoryCode) {
  const href = categoryPath(categoryCode);
  const categoryName = categories.find((item) => item.code === categoryCode)?.label || "разделу";
  return <div className="page-width"><p className="notice" role="status">Объявление снято с публикации. Посмотрите другие предложения.</p><Link className="button button-secondary" href={href}>Вернуться в раздел «{categoryName}»</Link></div>;
}

export async function generateMetadata({ params }: { params: Promise<RouteParams> }): Promise<Metadata> {
  const route = await params;
  const categoryCode = requestedCategory(route.category);
  if (!categoryCode || route.slug.length < 1) return {};

  try {
    const { listing } = await getListing(route.slug[route.slug.length - 1]);
    if ((listing.category_code || "cars") !== categoryCode) return {};
    return buildListingMetadata(listing);
  } catch (error) {
    if (error instanceof ApiClientError && (error.status === 404 || error.status === 410)) return {};
    return { alternates: { canonical: siteUrl(routePath(route)) } };
  }
}

export default async function CategoryListingDetailPage({ params }: { params: Promise<RouteParams> }) {
  const route = await params;
  const categoryCode = requestedCategory(route.category);
  if (!categoryCode || route.slug.length < 1) notFound();

  let listing: Listing;
  try {
    listing = (await getListing(route.slug[route.slug.length - 1])).listing;
  } catch (error) {
    if (error instanceof ApiClientError) {
      if (error.status === 404) notFound();
      if (error.status === 410) return gone(categoryCode);
    }
    return unavailable(categoryCode);
  }

  if ((listing.category_code || "cars") !== categoryCode) notFound();
  if (listing.status === "archived") return gone(categoryCode);
  if (listing.status !== "active" && listing.status !== "sold") notFound();

  const canonical = listingHref(listing);
  if (canonical !== routePath(route)) redirect(canonical);

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
