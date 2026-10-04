import type { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { POST } from "@/app/api/v1/[...path]/route";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("API proxy request headers", () => {
  it("forwards a company feed key without forwarding pilot Basic credentials", async () => {
    vi.stubEnv("API_INTERNAL_URL", "https://api.internal.test");
    const upstreamFetch = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", upstreamFetch);
    const request = new Request("http://localhost/api/v1/dealer/feeds/feed-1/api-imports", { method: "POST", headers: { "authorization": "Basic private-pilot-auth", "x-dealer-feed-token": "scoped-company-token", "content-type": "application/json" }, body: "{}" });
    await POST(request as NextRequest, { params: Promise.resolve({ path: ["dealer", "feeds", "feed-1", "api-imports"] }) });
    const init = upstreamFetch.mock.calls[0]?.[1] as RequestInit;
    const headers = new Headers(init.headers);
    expect(headers.get("x-dealer-feed-token")).toBe("scoped-company-token");
    expect(headers.has("authorization")).toBe(false);
  });

  it("forwards Bearer authorization only to the API feed import route", async () => {
    vi.stubEnv("API_INTERNAL_URL", "https://api.internal.test");
    const upstreamFetch = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", upstreamFetch);
    const request = new Request("http://localhost/api/v1/dealer/feeds/feed-1/api-imports", { method: "POST", headers: { "authorization": "Bearer scoped-company-token" }, body: "{}" });
    await POST(request as NextRequest, { params: Promise.resolve({ path: ["dealer", "feeds", "feed-1", "api-imports"] }) });
    const first = new Headers(upstreamFetch.mock.calls[0]?.[1]?.headers);
    expect(first.get("authorization")).toBe("Bearer scoped-company-token");
    await POST(request as NextRequest, { params: Promise.resolve({ path: ["account", "session"] }) });
    const second = new Headers(upstreamFetch.mock.calls[1]?.[1]?.headers);
    expect(second.has("authorization")).toBe(false);
  });

  it("forwards browser auth and CSRF headers but drops client IP headers", async () => {
    vi.stubEnv("API_INTERNAL_URL", "https://api.internal.test");
    const upstreamFetch = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) => new Response("{}", { status: 200, headers: { "X-Guest-Contact-Token": "signed-guest-proof" } })
    );
    vi.stubGlobal("fetch", upstreamFetch);

    const request = new Request("http://localhost/api/v1/account/session", {
      method: "POST",
      headers: {
        cookie: "session=browser-session",
        "x-csrf-token": "browser-csrf-token",
        "x-guest-contact-token": "signed-guest-proof",
        "x-forwarded-for": "203.0.113.10",
        "x-real-ip": "203.0.113.11",
        "content-type": "application/json"
      },
      body: JSON.stringify({})
    });

    const response = await POST(request as NextRequest, { params: Promise.resolve({ path: ["account", "session"] }) });

    expect(upstreamFetch).toHaveBeenCalledTimes(1);
    const [target, init] = upstreamFetch.mock.calls[0] as [RequestInfo | URL, RequestInit];
    const headers = new Headers(init.headers);

    expect(target).toBe("https://api.internal.test/api/v1/account/session");
    expect(headers.get("cookie")).toBe("session=browser-session");
    expect(headers.get("x-csrf-token")).toBe("browser-csrf-token");
    expect(headers.get("x-guest-contact-token")).toBe("signed-guest-proof");
    expect(headers.has("x-forwarded-for")).toBe(false);
    expect(headers.has("x-real-ip")).toBe(false);
    expect(response.headers.get("x-guest-contact-token")).toBe("signed-guest-proof");
  });
});
