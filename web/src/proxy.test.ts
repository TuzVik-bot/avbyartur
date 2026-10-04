import type { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { config, proxy } from "./proxy";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

function pageRequest(path: string, headers: Record<string, string> = {}, method = "GET") {
  return new Request(`http://localhost${path}`, { method, headers: { accept: "text/html", ...headers } }) as NextRequest;
}

describe("archived listing page status", () => {
  const listingId = "5d1e5683-7a58-4a7e-a3aa-58177dca2701";

  it("returns a branded 410 for a listing archived after publication", async () => {
    vi.stubEnv("API_INTERNAL_URL", "http://api.internal:8000");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 410 })));

    const response = await proxy(pageRequest(`/cars/audi/a3/${listingId}`));
    const html = await response.text();

    expect(response.status).toBe(410);
    expect(response.headers.get("x-robots-tag")).toContain("noindex");
    expect(html).toContain("Объявление снято с публикации");
    expect(html).toContain("cornflower");
    expect(fetch).toHaveBeenCalledWith(`http://api.internal:8000/api/v1/listings/${listingId}`, expect.any(Object));
  });

  it("returns an empty 410 for HEAD requests", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 410 })));

    const response = await proxy(pageRequest(`/cars/audi/a3/${listingId}`, {}, "HEAD"));

    expect(response.status).toBe(410);
    expect(await response.text()).toBe("");
  });

  it("continues normal routing when the API does not report an archived listing", async () => {
    const upstream = new Response("not archived", { status: 404 });
    const cancel = vi.spyOn(upstream.body!, "cancel");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(upstream));

    const response = await proxy(pageRequest(`/cars/audi/a3/${listingId}`));

    expect(response.headers.get("x-middleware-next")).toBe("1");
    expect(cancel).toHaveBeenCalledOnce();
  });

  it("does not issue the archival lookup during RSC navigation", async () => {
    const lookup = vi.fn();
    vi.stubGlobal("fetch", lookup);

    const response = await proxy(pageRequest(`/cars/audi/a3/${listingId}`, { rsc: "1", accept: "text/x-component" }));

    expect(lookup).not.toHaveBeenCalled();
    expect(response.headers.get("x-middleware-next")).toBe("1");
  });

  it("does not issue the archival lookup for catalog pages", async () => {
    const lookup = vi.fn();
    vi.stubGlobal("fetch", lookup);

    const response = await proxy(pageRequest("/cars/audi/a3"));

    expect(lookup).not.toHaveBeenCalled();
    expect(response.headers.get("x-middleware-next")).toBe("1");
  });
});

describe("Russian locale route aliases", () => {
  it("keeps the archived-listing matcher and adds only the Russian alias routes", () => {
    expect(config.matcher).toEqual(["/cars/:path*", "/ru", "/ru/:path*"]);
  });

  it("redirects a safe GET alias to its unprefixed route and preserves the query", async () => {
    const response = await proxy(pageRequest("/ru/cars?q=BMW&sort=price_asc"));

    expect(response.status).toBe(308);
    expect(response.headers.get("location")).toBe("http://localhost/cars?q=BMW&sort=price_asc");
  });

  it("redirects the Russian home alias and supports HEAD without changing the method", async () => {
    const response = await proxy(pageRequest("/ru?campaign=pilot", {}, "HEAD"));

    expect(response.status).toBe(308);
    expect(response.headers.get("location")).toBe("http://localhost/?campaign=pilot");
  });

  it.each([
    "/ru/api/v1/listings",
    "/ru/_next/static/chunk.js",
    "/ru/favicon.ico",
    "/ru/vehicles/silver-wagon.png",
    "/ru/icon",
    "/ru/apple-icon",
    "/ru/manifest",
    "/ru//cars/audi/a3/5d1e5683-7a58-4a7e-a3aa-58177dca2701",
    "/ru/cars%2fadmin",
    "/ru/cars%5cadmin",
  ])("passes machine and unsafe aliases through without redirects or API lookups: %s", async (path) => {
    const lookup = vi.fn();
    vi.stubGlobal("fetch", lookup);

    const response = await proxy(pageRequest(path));

    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
    expect(response.headers.get("x-middleware-next")).toBe("1");
    expect(lookup).not.toHaveBeenCalled();
  });

  it("does not create mutation aliases", async () => {
    const response = await proxy(pageRequest("/ru/cars", {}, "POST"));

    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
    expect(response.headers.get("x-middleware-next")).toBe("1");
  });
});
