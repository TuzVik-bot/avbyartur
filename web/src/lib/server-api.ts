import { headers } from "next/headers";
import { cache } from "react";
import { ApiClientError, searchPath } from "@/lib/api";
import { parseServerApiResponse, publicServerApiRequest, SERVER_API_TIMEOUT_MS, serverApiUrl } from "@/lib/public-server-api";
import type { components } from "@/lib/types.generated";
import type { AuthSession, CatalogItem, Company, CompanySummary, DealerReviewReport, DealerReviews, FavoriteListing, Listing, ListingPhoto, ListingSearch, ListingSummary, ListResponse, ModerationDealerReview, Report, UserNotificationList } from "@/lib/types";
import type { NotificationPreferences } from "@/lib/api";

export { SERVER_API_TIMEOUT_MS };

export async function serverApiRequest<T>(path: string): Promise<T> {
  const incoming = await headers();
  const requestHeaders = new Headers();
  const cookie = incoming.get("cookie");
  if (cookie) requestHeaders.set("cookie", cookie);
  const response = await fetch(serverApiUrl(path), {
    headers: requestHeaders,
    cache: "no-store",
    signal: AbortSignal.timeout(SERVER_API_TIMEOUT_MS)
  });
  return parseServerApiResponse<T>(response);
}

// The root layout, pages and helpers all ask for the session; cache() keeps it to one /me call per request.
export const getSessionServer = cache(async (): Promise<AuthSession | null> => {
  try { return await serverApiRequest<AuthSession>("me"); }
  catch (error) {
    if (error instanceof ApiClientError && error.status === 401) return null;
    throw error;
  }
});

export const serverApi = {
  listings: (search: ListingSearch = {}) => serverApiRequest<ListResponse<ListingSummary> & { fx?: { rate_date: string; usd_rate: string; scale: number } }>(searchPath(search).replace("/api/v1/", "")),
  listing: (id: string) => serverApiRequest<{ listing: Listing }>(`listings/${encodeURIComponent(id)}`),
  relatedListings: (id: string) => serverApiRequest<{ items: ListingSummary[] }>(`listings/${encodeURIComponent(id)}/related`),
  listingAnalytics: (id: string, options: { dateFrom?: string; dateTo?: string } = {}) => {
    const params = new URLSearchParams();
    if (options.dateFrom) params.set("date_from", options.dateFrom);
    if (options.dateTo) params.set("date_to", options.dateTo);
    const query = params.toString();
    return serverApiRequest<components["schemas"]["ListingAnalyticsOut"]>(`listings/${encodeURIComponent(id)}/analytics${query ? `?${query}` : ""}`);
  },
  billingTariffs: () => serverApiRequest<components["schemas"]["BillingTariffOut"][]>("billing/tariffs"),
  listingPromotionEligibility: (listingId: string) => serverApiRequest<{ promotable: boolean }>(`billing/listings/${encodeURIComponent(listingId)}/eligibility`),
  billingOrders: (page = 1, pageSize = 25) => serverApiRequest<components["schemas"]["BillingOrderListOut"]>(`billing/orders?page=${page}&page_size=${pageSize}`),
  billingOrder: (id: string) => serverApiRequest<components["schemas"]["BillingOrderOut"]>(`billing/orders/${encodeURIComponent(id)}`),
  catalog: (kind: "makes" | "models" | "generations" | "body-types" | "body-variants" | "modifications", params: { category_code?: ListingSearch["category_code"]; make_id?: string; model_id?: string; model_ids?: string; generation_id?: string; q?: string } = {}) => {
    const query = new URLSearchParams(params).toString();
    return publicServerApiRequest<{ items: CatalogItem[] }>(`catalog/${kind}${query ? `?${query}` : ""}`);
  },
  dealers: (page = 1) => serverApiRequest<ListResponse<CompanySummary>>(`dealers?${new URLSearchParams({ page: String(page) })}`),
  dealer: (slug: string, page = 1) => serverApiRequest<{ company: CompanySummary; listings: ListResponse<ListingSummary>; reviews: DealerReviews }>(`dealers/${encodeURIComponent(slug)}?${new URLSearchParams({ page: String(page) })}`),
  meListings: (page = 1, pageSize = 25) => {
    const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) }).toString();
    return serverApiRequest<ListResponse<Listing>>(`me/listings?${query}`);
  },
  favorites: () => serverApiRequest<{ items: FavoriteListing[] }>("me/favorites"),
  notifications: (options: { unreadOnly?: boolean; limit?: number } = {}) => {
    const params = new URLSearchParams();
    if (options.unreadOnly) params.set("unread_only", "true");
    if (options.limit !== undefined) params.set("limit", String(options.limit));
    const query = params.toString();
    return serverApiRequest<UserNotificationList>(`me/notifications${query ? `?${query}` : ""}`);
  },
  notificationPreferences: () => serverApiRequest<{ preferences: NotificationPreferences }>("me/notification-preferences"),
  company: () => serverApiRequest<{ company: Company | null }>("me/company"),
  moderationListings: (status: "pending_review" | "active" = "pending_review", page = 1) => {
    const query = new URLSearchParams({ status, page: String(page) }).toString();
    return serverApiRequest<ListResponse<Listing>>(`moderation/listings?${query}`);
  },
  moderationCompanies: () => serverApiRequest<{ items: Company[] }>("moderation/companies"),
  moderationReports: () => serverApiRequest<{ items: Report[] }>("moderation/reports"),
  moderationDealerReviews: (status: "pending" | "published" | "rejected" | "hidden" = "pending") => serverApiRequest<{ items: ModerationDealerReview[] }>(`moderation/dealer-reviews?${new URLSearchParams({ status })}`),
  moderationDealerReviewReports: (status: "open" | "resolved" = "open") => serverApiRequest<{ items: DealerReviewReport[] }>(`moderation/dealer-review-reports?${new URLSearchParams({ status })}`),
  regions: () => publicServerApiRequest<{ items: CatalogItem[] }>("locations/regions"),
  cities: (regionId = "") => publicServerApiRequest<{ items: CatalogItem[] }>(`locations/cities?region_id=${encodeURIComponent(regionId)}`),
  photos: (id: string) => serverApiRequest<{ items: ListingPhoto[] }>(`listings/${encodeURIComponent(id)}/photos`),
  customsRates: () => serverApiRequest<components["schemas"]["CustomsRatesResponse"]>("customs-calculator/rates"),
  customsRateHistory: (
    currency: components["schemas"]["CustomsRateHistoryResponse"]["currency"] = "USD",
    period: components["schemas"]["CustomsRateHistoryResponse"]["period"] = "90d"
  ) => {
    const query = new URLSearchParams({ currency, period }).toString();
    return serverApiRequest<components["schemas"]["CustomsRateHistoryResponse"]>(`customs-calculator/rates/history?${query}`);
  }
};

export async function getSavedListingIds() {
  try {
    if (!await getSessionServer()) return [];
    return (await serverApi.favorites()).items.map((item) => item.id);
  }
  catch { return []; }
}
