import type { MetadataRoute } from "next";
import { buildSitemapEntries, type SitemapListing } from "@/lib/seo";
import { serverApi } from "@/lib/server-api";
import type { CompanySummary, ListResponse } from "@/lib/types";

const PAGE_SIZE = "25";
const PAGE_BATCH_SIZE = 5;
const MAX_SITEMAP_PAGES = 2_000;

async function loadPages<T>(fetchPage: (page: number) => Promise<ListResponse<T>>): Promise<T[]> {
  const first = await fetchPage(1);
  const reportedPages = first.pagination?.pages ?? 1;
  const pageCount = Number.isSafeInteger(reportedPages)
    ? Math.min(Math.max(reportedPages, 1), MAX_SITEMAP_PAGES)
    : 1;
  const items = [...first.items];

  for (let start = 2; start <= pageCount; start += PAGE_BATCH_SIZE) {
    const end = Math.min(start + PAGE_BATCH_SIZE - 1, pageCount);
    const pages = await Promise.all(
      Array.from({ length: end - start + 1 }, (_, index) => fetchPage(start + index)),
    );
    for (const page of pages) items.push(...page.items);
  }

  return items;
}

async function loadActiveListings() {
  return loadPages<SitemapListing>((page) => serverApi.listings({
    page: String(page),
    page_size: PAGE_SIZE,
    sort: "newest",
  }));
}

async function loadApprovedDealers() {
  return loadPages<CompanySummary>((page) => serverApi.dealers(page));
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const [listingsResult, dealersResult] = await Promise.allSettled([
    loadActiveListings(),
    loadApprovedDealers(),
  ]);

  return buildSitemapEntries(
    listingsResult.status === "fulfilled" ? listingsResult.value : [],
    dealersResult.status === "fulfilled" ? dealersResult.value : [],
  );
}
