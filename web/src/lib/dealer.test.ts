import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ request: vi.fn(), idempotencyKey: vi.fn(() => "team-add-key") }));
vi.mock("@/lib/api", () => ({ apiRequest: mocks.request, createIdempotencyKey: mocks.idempotencyKey }));

import { dealerTeamApi, type DealerTeamMember } from "@/lib/dealer";

const member: DealerTeamMember = {
  id: "member-1", user_id: "user-1", email: "seller@example.test", display_name: "Продавец",
  role: "seller", status: "active", revision: 7, created_at: "2026-10-01T10:00:00Z"
};

afterEach(() => vi.clearAllMocks());

describe("dealer team API", () => {
  it("sends invites with an idempotency key and only the user ID and role", async () => {
    mocks.request.mockResolvedValueOnce({ member });
    await dealerTeamApi.add("user-1", "seller");
    expect(mocks.request).toHaveBeenCalledWith("dealer/team", {
      method: "POST", body: JSON.stringify({ user_id: "user-1", role: "seller" }),
      headers: { "Idempotency-Key": "team-add-key" }
    });
  });

  it("uses the member revision for every role or status change", async () => {
    mocks.request.mockResolvedValueOnce({ member: { ...member, status: "revoked", revision: 8 } });
    await dealerTeamApi.update(member, { status: "revoked" });
    expect(mocks.request).toHaveBeenCalledWith("dealer/team/member-1", {
      method: "PATCH", body: JSON.stringify({ status: "revoked", expected_revision: 7 })
    });
  });

  it("uses separate idempotent multipart requests for import preview and apply", async () => {
    mocks.request.mockResolvedValue({ run: {}, missing_candidates: [] });
    const file = new File(["stock"], "stock.csv", { type: "text/csv" });
    await dealerTeamApi.importFeedFile("feed/1", file, true, "preview-key");
    await dealerTeamApi.importFeedFile("feed/1", file, false, "apply-key", true);
    const first = mocks.request.mock.calls[0];
    const second = mocks.request.mock.calls[1];
    expect(first[0]).toBe("dealer/feeds/feed%2F1/imports?dry_run=true&complete_snapshot=false");
    expect(second[0]).toBe("dealer/feeds/feed%2F1/imports?dry_run=false&complete_snapshot=true");
    expect((first[1] as RequestInit).body).toBeInstanceOf(FormData);
    expect(new Headers((first[1] as RequestInit).headers).get("Idempotency-Key")).toBe("preview-key");
    expect(new Headers((second[1] as RequestInit).headers).get("Idempotency-Key")).toBe("apply-key");
  });

  it("encodes analytics date range and import row IDs", async () => {
    mocks.request.mockResolvedValueOnce({ period: {}, totals: {}, items: [] });
    mocks.request.mockResolvedValueOnce({ items: [] });
    await dealerTeamApi.analytics("2026-09-01", "2026-09-30");
    await dealerTeamApi.importRows("run/1");
    expect(mocks.request).toHaveBeenNthCalledWith(1, "dealer/analytics?from=2026-09-01&to=2026-09-30");
    expect(mocks.request).toHaveBeenNthCalledWith(2, "dealer/feed-imports/run%2F1/rows");
  });
});
