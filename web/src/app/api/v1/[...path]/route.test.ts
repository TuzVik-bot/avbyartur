import type { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GET, POST } from "@/app/api/v1/[...path]/route";

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

  it("forwards browser auth and CSRF headers and a single validated client IP", async () => {
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
    expect(headers.get("x-forwarded-for")).toBe("203.0.113.11");
    expect(headers.get("x-real-ip")).toBe("203.0.113.11");
    expect(response.headers.get("x-guest-contact-token")).toBe("signed-guest-proof");
  });
});

const upstreamOk = () => vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response("{}", { status: 200 }));

async function proxyWith(path: string[], headers: Record<string, string> = {}) {
  vi.stubEnv("API_INTERNAL_URL", "https://api.internal.test");
  const upstreamFetch = upstreamOk();
  vi.stubGlobal("fetch", upstreamFetch);
  const request = new Request("http://localhost/api/v1/listings", { method: "GET", headers });
  const response = await GET(request as NextRequest, { params: Promise.resolve({ path }) });
  return { response, upstreamFetch };
}

describe("API proxy client IP forwarding", () => {
  it("uses only the first forwarded entry when x-real-ip is absent", async () => {
    const { upstreamFetch } = await proxyWith(["listings"], { "x-forwarded-for": "198.51.100.7, 10.0.0.1, 10.0.0.2" });
    const headers = new Headers(upstreamFetch.mock.calls[0]?.[1]?.headers);
    expect(headers.get("x-forwarded-for")).toBe("198.51.100.7");
    expect(headers.get("x-real-ip")).toBe("198.51.100.7");
  });

  it("accepts IPv6 client addresses", async () => {
    const { upstreamFetch } = await proxyWith(["listings"], { "x-real-ip": "2001:db8::1" });
    const headers = new Headers(upstreamFetch.mock.calls[0]?.[1]?.headers);
    expect(headers.get("x-forwarded-for")).toBe("2001:db8::1");
  });

  it.each([
    [{ "x-real-ip": "not-an-ip" }],
    [{ "x-forwarded-for": "evil.example, 198.51.100.7" }],
    [{}],
  ])("drops invalid or missing client IP headers %#", async (incoming) => {
    const { upstreamFetch } = await proxyWith(["listings"], incoming);
    const headers = new Headers(upstreamFetch.mock.calls[0]?.[1]?.headers);
    expect(headers.has("x-forwarded-for")).toBe(false);
    expect(headers.has("x-real-ip")).toBe(false);
  });
});

describe("API proxy path validation", () => {
  it.each([
    [["..", "admin"]],
    [["listings", "..", "..", "docs"]],
    [["."]],
    [["listings", ""]],
    [["%2e%2e", "docs"]],
    [["%2E%2E"]],
  ])("rejects traversal segments %j without calling the API", async (path) => {
    const { response, upstreamFetch } = await proxyWith(path);
    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({ message: "Неверный адрес запроса." });
    expect(upstreamFetch).not.toHaveBeenCalled();
  });

  it("keeps ordinary segments with encoded characters inside the API prefix", async () => {
    const { response, upstreamFetch } = await proxyWith(["listings", "a b"]);
    expect(response.status).toBe(200);
    expect(upstreamFetch.mock.calls[0]?.[0]).toBe("https://api.internal.test/api/v1/listings/a%20b");
  });
});
