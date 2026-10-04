import { apiRequest } from "@/lib/api";

export type CatalogRequestStatus = "pending" | "resolved" | "rejected";
export type CatalogRequestDecision = "resolve" | "reject";

export type CatalogRequestCatalogNode = {
  id: string;
  name: string;
  year_from?: number | null;
  year_to?: number | null;
};

export type CatalogRequestSnapshot = {
  catalog: {
    make: CatalogRequestCatalogNode | null;
    model: CatalogRequestCatalogNode | null;
    generation: CatalogRequestCatalogNode | null;
    body_type: CatalogRequestCatalogNode | null;
    body_variant: CatalogRequestCatalogNode | null;
  };
  manual_identity: { make: string | null; model: string | null };
  manual_parameters: {
    year: number | null;
    mileage_km: number | null;
    engine_volume_l: string | null;
    power_hp: number | null;
    fuel: string | null;
    transmission: string | null;
    drive: string | null;
  };
};

export type CatalogRequestMatch = {
  id: string;
  slug: string;
  name: string;
  make: CatalogRequestCatalogNode;
  model: CatalogRequestCatalogNode;
  generation: CatalogRequestCatalogNode;
  source?: { name: "Drom"; id: string | null; url: string | null } | null;
  specs?: {
    engine_code: string | null;
    frame_code: string | null;
    engine_l: number | null;
    power_hp: number | null;
    fuel: string | null;
    transmission: string | null;
    drive: string | null;
    production_period_raw: string | null;
    summary_raw: string | null;
  } | null;
};

export type CatalogRequest = {
  id: string;
  listing_id: string;
  listing_revision: number;
  status: CatalogRequestStatus;
  revision: number;
  snapshot: CatalogRequestSnapshot;
  manual_modification_name: string | null;
  note: string | null;
  resolved_modification: CatalogRequestMatch | null;
  review_reason: string | null;
  created_at: string;
  reviewed_at: string | null;
};

export type CatalogRequestCreateInput = {
  expected_listing_revision: number;
  manual_modification_name: string | null;
  note: string | null;
};

export type CatalogRequestReviewInput = {
  expected_revision: number;
  decision: CatalogRequestDecision;
  reason: string;
  resolved_modification_id?: string | null;
};

export type CatalogRequestPage = {
  items: CatalogRequest[];
  total: number;
  page: number;
  page_size: number;
};

export type CatalogRequestQueueOptions = {
  status?: CatalogRequestStatus;
  page?: number;
  page_size?: number;
};

function encodedId(id: string) {
  return encodeURIComponent(id);
}

export const catalogRequestsApi = {
  listForListing(listingId: string) {
    return apiRequest<{ items: CatalogRequest[] }>(
      "me/listings/" + encodedId(listingId) + "/catalog-requests",
    );
  },
  createForListing(
    listingId: string,
    data: CatalogRequestCreateInput,
    idempotencyKey: string,
  ) {
    return apiRequest<{ request: CatalogRequest }>(
      "me/listings/" + encodedId(listingId) + "/catalog-requests",
      {
        method: "POST",
        body: JSON.stringify(data),
        headers: { "Idempotency-Key": idempotencyKey },
      },
    );
  },
  listModeration(options: CatalogRequestQueueOptions = {}) {
    const query = new URLSearchParams();
    if (options.status) query.set("status", options.status);
    if (options.page !== undefined) query.set("page", String(options.page));
    if (options.page_size !== undefined) query.set("page_size", String(options.page_size));
    const suffix = query.size ? "?" + query.toString() : "";
    return apiRequest<CatalogRequestPage>("moderation/catalog-requests" + suffix);
  },
  searchMatches(requestId: string, query: string) {
    const params = new URLSearchParams({ q: query });
    return apiRequest<{ items: CatalogRequestMatch[] }>(
      "moderation/catalog-requests/" + encodedId(requestId) + "/matches?" + params.toString(),
    );
  },
  review(requestId: string, data: CatalogRequestReviewInput) {
    return apiRequest<{ request: CatalogRequest }>(
      "moderation/catalog-requests/" + encodedId(requestId) + "/review",
      { method: "POST", body: JSON.stringify(data) },
    );
  },
};
