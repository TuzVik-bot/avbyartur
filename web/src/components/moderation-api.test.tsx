import { afterEach, describe, expect, it, vi } from "vitest";
import { serverApi } from "@/lib/server-api";

vi.mock("next/headers", () => ({ headers: async () => new Headers() }));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("moderation listing status query", () => {
  it("requests the selected queue status and defaults to pending review", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    }));
    vi.stubGlobal("fetch", fetchMock);

    await serverApi.moderationListings("active", 3);
    await serverApi.moderationListings();

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "http://127.0.0.1:8000/api/v1/moderation/listings?status=active&page=3",
      "http://127.0.0.1:8000/api/v1/moderation/listings?status=pending_review&page=1"
    ]);
  });
});
