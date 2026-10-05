import { headers } from "next/headers";
import { ApiClientError, internalApiBase, searchPath } from "@/lib/api";
import type { components } from "@/lib/types.generated";
import type { ApiErrorShape, AuthSession, CatalogItem, Company, CompanySummary, Listing, ListingPhoto, ListingSearch, ListingSummary, ListResponse, Report, UserNotificationList } from "@/lib/types";
import type { NotificationPreferences } from "@/lib/api";

export async function serverApiRequest<T>(path: string, options: { forwardCookies?: boolean } = {}): Promise<T> {
  const requestHeaders = new Headers();
  if (options.forwardCookies !== false) {
    const incoming = await headers();
    const cookie = incoming.get("cookie");
    if (cookie) requestHeaders.set("cookie", cookie);
  }
  const response = await fetch(`${internalApiBase()}/${path.replace(/^\//, "")}`, { headers: requestHeaders, cache: "no-store" });
  const payload: unknown = await response.json().catch(() => undefined);
  if (!response.ok) throw new ApiClientError(response.status, (payload || {}) as Partial<ApiErrorShape>);
  return payload as T;
}

export async function getSessionServer(): Promise<AuthSession | null> {
  try { return await serverApiRequest<AuthSession>("me"); }
  catch (error) {
    if (error instanceof ApiClientError && error.status === 401) return null;
    throw error;
  }
}

export const serverApi = {
  vinCheckStatus: () => serverApiRequest<components["schemas"]["VinCheckStatusOut"]>("vin-check/status", { forwardCookies: false }),
  customsRates: () => serverApiRequest<components["schemas"]["CustomsRatesResponse"]>("customs-calculator/rates", { forwardCookies: false }),
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
  billingOrders: (page = 1, pageSize = 25) => serverApiRequest<components["schemas"]["BillingOrderListOut"]>(`billing/orders?page=${page}&page_size=${pageSize}`),
  billingOrder: (id: string) => serverApiRequest<components["schemas"]["BillingOrderOut"]>(`billing/orders/${encodeURIComponent(id)}`),
  catalog: (kind: "makes" | "models" | "generations" | "body-types" | "body-variants" | "modifications", params: Record<string, string> = {}) => {
    const query = new URLSearchParams(params).toString();
    return serverApiRequest<{ items: CatalogItem[] }>(`catalog/${kind}${query ? `?${query}` : ""}`);
  },
  dealers: (page = 1) => serverApiRequest<ListResponse<CompanySummary>>(`dealers?${new URLSearchParams({ page: String(page) })}`),
  dealer: (slug: string, page = 1) => serverApiRequest<{ company: CompanySummary; listings: ListResponse<ListingSummary> }>(`dealers/${encodeURIComponent(slug)}?${new URLSearchParams({ page: String(page) })}`),
  meListings: (page = 1, pageSize = 25) => {
    const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) }).toString();
    return serverApiRequest<ListResponse<Listing>>(`me/listings?${query}`);
  },
  favorites: () => serverApiRequest<{ items: ListingSummary[] }>("me/favorites"),
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
  regions: () => serverApiRequest<{ items: CatalogItem[] }>("locations/regions"),
  cities: (regionId = "") => serverApiRequest<{ items: CatalogItem[] }>(`locations/cities?region_id=${encodeURIComponent(regionId)}`),
  photos: (id: string) => serverApiRequest<{ items: ListingPhoto[] }>(`listings/${encodeURIComponent(id)}/photos`)
};

export async function getSavedListingIds() {
  try {
    if (!await getSessionServer()) return [];
    return (await serverApi.favorites()).items.map((item) => item.id);
  }
  catch { return []; }
}
