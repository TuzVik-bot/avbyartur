import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "@/lib/api";
import { catalogRequestsApi } from "@/lib/catalog-requests";

vi.mock("@/lib/api", () => ({ apiRequest: vi.fn() }));

describe("catalog request API client", () => {
  beforeEach(() => vi.mocked(apiRequest).mockReset());

  it("uses listing-scoped paths and the caller's stable idempotency key", async () => {
    vi.mocked(apiRequest).mockResolvedValue({ items: [] });
    await catalogRequestsApi.listForListing("listing / one");
    expect(apiRequest).toHaveBeenCalledWith(
      "me/listings/listing%20%2F%20one/catalog-requests"
    );

    await catalogRequestsApi.createForListing(
      "listing / one",
      {
        expected_listing_revision: 7,
        manual_modification_name: "2.0 TDI",
        note: "Ручные параметры",
      },
      "retry-stable-key",
    );
    expect(apiRequest).toHaveBeenLastCalledWith(
      "me/listings/listing%20%2F%20one/catalog-requests",
      {
        method: "POST",
        body: JSON.stringify({
          expected_listing_revision: 7,
          manual_modification_name: "2.0 TDI",
          note: "Ручные параметры",
        }),
        headers: { "Idempotency-Key": "retry-stable-key" },
      },
    );
  });

  it("searches moderator matches and reviews with a revision and reason", async () => {
    vi.mocked(apiRequest).mockResolvedValue({ items: [] });
    await catalogRequestsApi.searchMatches("request-1", "2.0 AT");
    expect(apiRequest).toHaveBeenCalledWith(
      "moderation/catalog-requests/request-1/matches?q=2.0+AT",
    );

    await catalogRequestsApi.review("request-1", {
      expected_revision: 3,
      decision: "resolve",
      reason: "Подтверждено по записи каталога.",
      resolved_modification_id: "mod-1",
    });
    expect(apiRequest).toHaveBeenLastCalledWith(
      "moderation/catalog-requests/request-1/review",
      {
        method: "POST",
        body: JSON.stringify({
          expected_revision: 3,
          decision: "resolve",
          reason: "Подтверждено по записи каталога.",
          resolved_modification_id: "mod-1",
        }),
      },
    );
  });
});
