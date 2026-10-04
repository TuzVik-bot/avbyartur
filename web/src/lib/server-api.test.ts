import { afterEach, describe, expect, it, vi } from "vitest";
import { requireSession } from "@/lib/server";
import { getSavedListingIds, getSessionServer, serverApi } from "@/lib/server-api";

const mocks = vi.hoisted(() => ({
  redirect: vi.fn((url: string) => { throw new Error(`NEXT_REDIRECT:${url}`); })
}));

vi.mock("next/navigation", () => ({ redirect: mocks.redirect }));

vi.mock("next/headers", () => ({
  headers: async () => new Headers({ cookie: "pilot_session=test-session" })
}));

afterEach(() => {
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
