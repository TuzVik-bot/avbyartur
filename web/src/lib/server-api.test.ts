import { afterEach, describe, expect, it, vi } from "vitest";
import { requireSession } from "@/lib/server";
import { getSavedListingIds, getSessionServer, SERVER_API_TIMEOUT_MS, serverApi } from "@/lib/server-api";
import { clearPublicReferenceCache, MAX_PUBLIC_REFERENCE_CACHE_ENTRIES, publicReferenceCacheSize } from "@/lib/public-server-api";

const mocks = vi.hoisted(() => ({
  redirect: vi.fn((url: string) => { throw new Error(`NEXT_REDIRECT:${url}`); })
}));

vi.mock("next/navigation", () => ({ redirect: mocks.redirect }));

vi.mock("next/headers", () => ({
  headers: async () => new Headers({ cookie: "pilot_session=test-session" })
}));

afterEach(() => {
  clearPublicReferenceCache();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("saved listing IDs", () => {
  it("loads favorites only after a valid server session", async () => {
    const request = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ user: { id: "user-1" }, csrf_token: "token" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [{ id: "listing-1" }, { id: "listing-2" }] }), { status: 200 }));
    vi.stubGlobal("fetch", request);

    await expect(getSavedListingIds()).resolves.toEqual(["listing-1", "listing-2"]);

    expect(request).toHaveBeenCalledTimes(2);
    expect(String(request.mock.calls[0][0])).toContain("/api/v1/me");
    expect(String(request.mock.calls[1][0])).toContain("/api/v1/me/favorites");
  });

  it("does not query another user's favorites when the session is missing", async () => {
    const request = vi.fn().mockResolvedValueOnce(new Response("{}", { status: 401 }));
    vi.stubGlobal("fetch", request);

    await expect(getSavedListingIds()).resolves.toEqual([]);

    expect(request).toHaveBeenCalledOnce();
  });

  it("keeps public favorite decorations optional during a session API outage", async () => {
    const request = vi.fn().mockResolvedValueOnce(new Response(
      JSON.stringify({ code: "service_unavailable", message: "Временно недоступно" }),
      { status: 503 }
    ));
    vi.stubGlobal("fetch", request);

    await expect(getSavedListingIds()).resolves.toEqual([]);

    expect(request).toHaveBeenCalledOnce();
  });

  it("passes explicit pagination to the owner listings endpoint", async () => {
    const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], pagination: { page: 2, page_size: 25, total: 50, pages: 2 } }), { status: 200 }));
    vi.stubGlobal("fetch", request);

    await serverApi.meListings(2);

    expect(String(request.mock.calls[0][0])).toContain("/api/v1/me/listings?page=2&page_size=25");
  });

  it("loads the authenticated notification inbox with a bounded limit", async () => {
    const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], unread_count: 0 }), { status: 200 }));
    vi.stubGlobal("fetch", request);

    await expect(serverApi.notifications({ limit: 50 })).resolves.toEqual({ items: [], unread_count: 0 });

    expect(String(request.mock.calls[0][0])).toContain("/api/v1/me/notifications?limit=50");
    expect(new Headers((request.mock.calls[0][1] as RequestInit).headers).get("cookie")).toBe("pilot_session=test-session");
  });
});

describe("server session lookup", () => {
  it("treats only an unauthorized response as a missing session", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response(
      JSON.stringify({ code: "service_unavailable", message: "Временно недоступно" }),
      { status: 503 }
    )));

    await expect(getSessionServer()).rejects.toMatchObject({ name: "ApiClientError", status: 503 });
  });

  it("propagates a network failure instead of treating it as logout", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValueOnce(new TypeError("fetch failed")));

    await expect(getSessionServer()).rejects.toThrow("fetch failed");
  });

  it("does not redirect a protected route when the session API is unavailable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response(
      JSON.stringify({ code: "service_unavailable", message: "Временно недоступно" }),
      { status: 503 }
    )));

    await expect(requireSession("/account/notifications")).rejects.toMatchObject({ name: "ApiClientError", status: 503 });
    expect(mocks.redirect).not.toHaveBeenCalled();
  });

  it("redirects a protected route when the session endpoint returns 401", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response("{}", { status: 401 })));
    mocks.redirect.mockImplementationOnce((url: string) => { throw new Error(`NEXT_REDIRECT:${url}`); });

    await expect(requireSession("/account/notifications")).rejects.toThrow("NEXT_REDIRECT:/login?next=%2Faccount%2Fnotifications");
    expect(mocks.redirect).toHaveBeenCalledWith("/login?next=%2Faccount%2Fnotifications");
  });
});

describe("server API timeouts", () => {
  it("bounds every session-bound SSR request with an abort signal", async () => {
    const timeout = vi.spyOn(AbortSignal, "timeout");
    const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [] }), { status: 200 }));
    vi.stubGlobal("fetch", request);

    await serverApi.favorites();

    expect(timeout).toHaveBeenCalledWith(SERVER_API_TIMEOUT_MS);
    expect((request.mock.calls[0][1] as RequestInit).signal).toBeInstanceOf(AbortSignal);
    timeout.mockRestore();
  });

  it("uses a five second budget", () => {
    expect(SERVER_API_TIMEOUT_MS).toBe(5000);
  });
});

describe("public reference data", () => {
  const ok = (items: unknown[] = []) => new Response(JSON.stringify({ items }), { status: 200 });

  it("fetches catalog, regions and cities without forwarding visitor cookies", async () => {
    const request = vi.fn().mockImplementation(async () => ok());
    vi.stubGlobal("fetch", request);

    await serverApi.catalog("makes", { category_code: "cars" });
    await serverApi.regions();
    await serverApi.cities("region-1");

    expect(request).toHaveBeenCalledTimes(3);
    for (const [, init] of request.mock.calls) {
      expect(new Headers((init as RequestInit).headers).get("cookie")).toBeNull();
      expect((init as RequestInit).signal).toBeInstanceOf(AbortSignal);
    }
    expect(String(request.mock.calls[0][0])).toContain("/api/v1/catalog/makes?category_code=cars");
    expect(String(request.mock.calls[2][0])).toContain("/api/v1/locations/cities?region_id=region-1");
  });

  it("memoizes identical reference requests in-process for five minutes", async () => {
    vi.useFakeTimers();
    const request = vi.fn().mockImplementation(async () => ok([{ id: "make-1" }]));
    vi.stubGlobal("fetch", request);

    await expect(serverApi.catalog("makes")).resolves.toEqual({ items: [{ id: "make-1" }] });
    await expect(serverApi.catalog("makes")).resolves.toEqual({ items: [{ id: "make-1" }] });
    await serverApi.catalog("models", { make_id: "make-1" });
    expect(request).toHaveBeenCalledTimes(2);

    vi.advanceTimersByTime(5 * 60 * 1000 + 1);
    await serverApi.catalog("makes");
    expect(request).toHaveBeenCalledTimes(3);
  });

  it("does not cache a failed reference request", async () => {
    const request = vi.fn()
      .mockResolvedValueOnce(new Response("{}", { status: 503 }))
      .mockResolvedValueOnce(ok([{ id: "region-1" }]));
    vi.stubGlobal("fetch", request);

    await expect(serverApi.regions()).rejects.toMatchObject({ name: "ApiClientError", status: 503 });
    await expect(serverApi.regions()).resolves.toEqual({ items: [{ id: "region-1" }] });
    expect(request).toHaveBeenCalledTimes(2);
  });

  it("starts over after the cache is cleared", async () => {
    const request = vi.fn().mockImplementation(async () => ok());
    vi.stubGlobal("fetch", request);

    await serverApi.regions();
    clearPublicReferenceCache();
    await serverApi.regions();

    expect(request).toHaveBeenCalledTimes(2);
  });
});

describe("public reference cache bounds", () => {
  it("never grows past its entry limit when visitors request arbitrary catalog queries", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async () => new Response(JSON.stringify({ items: [] }), { status: 200 })));

    for (let index = 0; index < MAX_PUBLIC_REFERENCE_CACHE_ENTRIES + 25; index += 1) {
      await serverApi.catalog("makes", { q: `slug-${index}` });
    }

    expect(publicReferenceCacheSize()).toBe(MAX_PUBLIC_REFERENCE_CACHE_ENTRIES);
  });
});
