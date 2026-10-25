import { apiRequest, createIdempotencyKey } from "@/lib/api";
import type { components } from "@/lib/types.generated";

export type DealerTeamMember = components["schemas"]["DealerTeamMemberOut"];
export type DealerTeamRole = DealerTeamMember["role"];
export type DealerTeamMemberRole = Exclude<DealerTeamRole, "owner">;
export type DealerTeamStatus = DealerTeamMember["status"];
export type DealerTeamList = components["schemas"]["DealerTeamListOut"];
export type DealerTeamPatch = components["schemas"]["DealerTeamPatch"];
type GeneratedDealerFeed = components["schemas"]["DealerFeedOut"];
export type DealerFeed = GeneratedDealerFeed & {
  latest_import: DealerFeedImportRun | null;
  last_successful_import_at: string | null;
  last_successful_import_age_seconds: number | null;
};
export type DealerFeedCreate = components["schemas"]["DealerFeedCreate"];
export type DealerFeedImportRun = components["schemas"]["DealerFeedImportRunOut"];
export type DealerFeedImportHistoryItem = { feed_name: string; run: DealerFeedImportRun };
export type DealerFeedImportHistory = { items: DealerFeedImportHistoryItem[]; next_cursor: string | null };
export type DealerFeedImportRow = components["schemas"]["DealerFeedImportRowOut"];
export type DealerFeedMissingCandidate = components["schemas"]["DealerFeedMissingCandidateOut"];
export type DealerFeedMissingConfirmation = components["schemas"]["DealerFeedMissingCandidateConfirmation"];
export type DealerFeedPolicyPatch = Pick<components["schemas"]["DealerFeedPatch"], "manual_conflict_policy" | "missing_retirement_enabled" | "missing_retirement_delay_hours">;
type GeneratedDealerAnalytics = components["schemas"]["DealerAnalyticsOut"];
type GeneratedDealerAnalyticsTotals = GeneratedDealerAnalytics["totals"];
type GeneratedDealerAnalyticsItem = GeneratedDealerAnalytics["items"][number];
export type DealerAnalytics = Omit<GeneratedDealerAnalytics, "totals" | "items"> & {
  totals: Omit<GeneratedDealerAnalyticsTotals, "company_clicks"> & { company_clicks: number };
  items: Array<Omit<GeneratedDealerAnalyticsItem, "company_clicks"> & { company_clicks: number }>;
};

export const dealerTeamApi = {
  list() {
    return apiRequest<DealerTeamList>("dealer/team");
  },
  add(user_id: string, role: DealerTeamMemberRole, idempotencyKey = createIdempotencyKey()) {
    return apiRequest<{ member: DealerTeamMember }>("dealer/team", {
      method: "POST",
      body: JSON.stringify({ user_id, role }),
      headers: { "Idempotency-Key": idempotencyKey }
    });
  },
  update(member: DealerTeamMember, change: Omit<DealerTeamPatch, "expected_revision">) {
    return apiRequest<{ member: DealerTeamMember }>(`dealer/team/${encodeURIComponent(member.id)}`, {
      method: "PATCH",
      body: JSON.stringify({ ...change, expected_revision: member.revision })
    });
  },
  feeds() {
    return apiRequest<{ items: DealerFeed[] }>("dealer/feeds");
  },
  createFeed(payload: DealerFeedCreate) {
    return apiRequest<{ feed: DealerFeed; api_token?: string | null }>("dealer/feeds", { method: "POST", body: JSON.stringify(payload) });
  },
  updateFeedStatus(feed: DealerFeed, status: DealerFeed["status"]) {
    return apiRequest<{ feed: DealerFeed; api_token?: string | null }>(`dealer/feeds/${encodeURIComponent(feed.id)}`, {
      method: "PATCH", body: JSON.stringify({ status })
    });
  },
  updateFeedPolicy(feedId: string, policy: DealerFeedPolicyPatch) {
    return apiRequest<{ feed: DealerFeed; api_token?: string | null }>(`dealer/feeds/${encodeURIComponent(feedId)}`, {
      method: "PATCH", body: JSON.stringify(policy)
    });
  },
  rotateFeedToken(feedId: string) {
    return apiRequest<components["schemas"]["DealerFeedTokenOut"]>(`dealer/feeds/${encodeURIComponent(feedId)}/rotate-token`, { method: "POST", body: JSON.stringify({}) });
  },
  importFeedFile(feedId: string, file: File, dryRun: boolean, idempotencyKey: string, completeSnapshot = false) {
    const formData = new FormData();
    formData.set("file", file);
    return apiRequest<{ run: DealerFeedImportRun; missing_candidates: DealerFeedMissingCandidate[] }>(`dealer/feeds/${encodeURIComponent(feedId)}/imports?dry_run=${dryRun ? "true" : "false"}&complete_snapshot=${completeSnapshot ? "true" : "false"}`, {
      method: "POST", body: formData, headers: { "Idempotency-Key": idempotencyKey }
    });
  },
  missingCandidates(feedId: string) {
    return apiRequest<{ items: DealerFeedMissingCandidate[] }>(`dealer/feeds/${encodeURIComponent(feedId)}/missing-candidates`);
  },
  confirmMissingCandidate(feedId: string, item: DealerFeedMissingConfirmation, idempotencyKey: string) {
    return apiRequest<{ run: DealerFeedImportRun; paused_external_ids: string[] }>(`dealer/feeds/${encodeURIComponent(feedId)}/missing-candidates/pause`, {
      method: "POST",
      body: JSON.stringify({ items: [item] }),
      headers: { "Idempotency-Key": idempotencyKey }
    });
  },
  importRun(runId: string) {
    return apiRequest<{ run: DealerFeedImportRun }>(`dealer/feed-imports/${encodeURIComponent(runId)}`);
  },
  importHistory(limit = 20, cursor?: string | null) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (cursor) params.set("cursor", cursor);
    return apiRequest<DealerFeedImportHistory>(`dealer/feed-imports?${params.toString()}`);
  },
  importRows(runId: string) {
    return apiRequest<{ items: DealerFeedImportRow[] }>(`dealer/feed-imports/${encodeURIComponent(runId)}/rows`);
  },
  analytics(from?: string, to?: string) {
    const params = new URLSearchParams();
    if (from) params.set("from", from);
    if (to) params.set("to", to);
    const query = params.toString();
    return apiRequest<DealerAnalytics>(`dealer/analytics${query ? `?${query}` : ""}`);
  }
};
