import type { MetadataRoute } from "next";
import { editorialArticlePaths } from "@/lib/editorial-articles";
import { buildSitemapEntries, type SitemapListing } from "@/lib/seo";
import { loadManagedArticleSummaries } from "@/lib/public-articles";
import { serverApi } from "@/lib/server-api";
import type { CompanySummary, ListResponse } from "@/lib/types";
import { siteUrl } from "@/lib/site-config";

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

// Managed articles are capped at 1000 (10 pages x 100 in loadManagedArticleSummaries).
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const [listingsResult, dealersResult, managedResult] = await Promise.allSettled([
    loadActiveListings(),
    loadApprovedDealers(),
    loadManagedArticleSummaries(),
  ]);
  const managedArticles = managedResult.status === "fulfilled" ? managedResult.value : [];
  const staticPaths = new Set<string>(editorialArticlePaths);
  const managedPaths = managedArticles
    .map((article) => `/useful-information/articles/${article.slug}`)
    .filter((path) => !staticPaths.has(path));

  const entries = buildSitemapEntries(
    listingsResult.status === "fulfilled" ? listingsResult.value : [],
    dealersResult.status === "fulfilled" ? dealersResult.value : [],
  );

  return [
    ...entries,
    ...editorialArticlePaths.map((path) => ({ url: siteUrl(path) })),
    ...managedPaths.map((path) => ({ url: siteUrl(path) })),
  ];
}
