import { renderToStaticMarkup } from "react-dom/server";
import { createElement, type ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/lib/api";

const mocks = vi.hoisted(() => ({
  listing: vi.fn(),
  listings: vi.fn(),
  catalog: vi.fn(),
  favorites: vi.fn(),
  relatedListings: vi.fn(),
  session: vi.fn(),
  notFound: vi.fn((): never => { throw new Error("NEXT_NOT_FOUND"); }),
  redirect: vi.fn((href: string): never => { throw new Error(`REDIRECT:${href}`); })
}));

vi.mock("next/navigation", () => ({ notFound: mocks.notFound, redirect: mocks.redirect }));
vi.mock("next/link", () => ({ default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a> }));
vi.mock("@/lib/server-api", () => ({ serverApi: { listing: mocks.listing, listings: mocks.listings, catalog: mocks.catalog, favorites: mocks.favorites, relatedListings: mocks.relatedListings }, getSessionServer: mocks.session }));
vi.mock("@/components/search-route", () => ({ SearchRoute: (props: unknown) => createElement("div", { "data-search": JSON.stringify(props) }), getCatalogCities: vi.fn() }));
vi.mock("@/components/listing-card", () => ({ ListingCard: (props: { listing: { id: string } }) => createElement("div", { "data-similar": props.listing.id }) }));
vi.mock("@/components/listing-detail", () => ({ ListingDetail: (props: { initialSaved: boolean }) => createElement("div", { "data-initial-saved": String(props.initialSaved) }) }));

import CarsBySlugPage, { generateMetadata } from "@/app/cars/[...slug]/page";

const params = { slug: ["toyota", "corolla", "listing-1"] };

beforeEach(() => {
  mocks.listing.mockReset();
  mocks.listings.mockReset();
  mocks.catalog.mockReset();
  mocks.favorites.mockReset();
  mocks.relatedListings.mockReset().mockResolvedValue({ items: [] });
  mocks.session.mockReset().mockResolvedValue(null);
  mocks.notFound.mockClear();
  mocks.redirect.mockClear();
});

describe("listing route API failures", () => {
  it("sets a self-canonical for public listings and renders schema without private contacts", async () => {
    const publicListing = {
      id: "listing-1",
      slug: "listing-1",
      title: "BMW 320",
      make: { id: "make-1", slug: "bmw", name: "BMW" },
      model: { id: "model-1", slug: "3-series", name: "3 Series" },
      year: 2020,
      mileage_km: 45_000,
      fuel: "petrol",
      transmission: "automatic",
      drive: "rear",
      body_type: "sedan",
      price: { amount: "25000", currency: "USD" },
      cover_url: "/api/v1/photos/photo-1/768",
      photo_urls: ["/api/v1/photos/photo-1/768"],
      seller: { type: "private", id: "seller-1", name: "Продавец" },
      status: "active",
      description: "Приватный контакт +375291234567",
    };
    mocks.listing.mockResolvedValue({ listing: publicListing });

    const publicParams = { slug: ["bmw", "3-series", "listing-1"] };
    const metadata = await generateMetadata({ params: Promise.resolve(publicParams) });
    const html = renderToStaticMarkup(await CarsBySlugPage({ params: Promise.resolve(publicParams) }));

    expect(metadata.alternates?.canonical).toBe("https://xn--80aeylebmo7f.xn--90ais/cars/bmw/3-series/listing-1");
    expect(html).toContain('type="application/ld+json"');
    expect(html).toContain('"@type":"Car"');
    expect(html).not.toContain("+375291234567");
  });

  it("renders a retryable service error when listing API is unavailable", async () => {
    mocks.listing.mockRejectedValueOnce(new ApiClientError(503, { message: "Недоступно" }));

    const html = renderToStaticMarkup(await CarsBySlugPage({ params: Promise.resolve(params) }));

    expect(html).toContain("Не удалось загрузить объявление");
    expect(html).toContain('href="/cars"');
    expect(mocks.notFound).not.toHaveBeenCalled();
  });

  it("returns 404 when a listing does not exist", async () => {
    mocks.listing.mockRejectedValueOnce(new ApiClientError(404, { message: "Не найдено" }));

    await expect(CarsBySlugPage({ params: Promise.resolve(params) })).rejects.toThrow("NEXT_NOT_FOUND");
  });

  it("renders a gone state for an archived listing instead of converting 410 to 404", async () => {
    mocks.listing.mockRejectedValueOnce(new ApiClientError(410, { code: "gone", message: "Снято с публикации" }));

    const html = renderToStaticMarkup(await CarsBySlugPage({ params: Promise.resolve(params) }));

    expect(html).toContain("Объявление снято с публикации");
    expect(html).toContain('href="/cars"');
    expect(mocks.notFound).not.toHaveBeenCalled();
  });

  it("keeps an archived listing response in the gone state", async () => {
    mocks.listing.mockResolvedValueOnce({ listing: {
      id: "listing-1", slug: "listing-1", status: "archived",
      make: { slug: "toyota" }, model: { slug: "corolla" }
    } });

    const html = renderToStaticMarkup(await CarsBySlugPage({ params: Promise.resolve(params) }));

    expect(html).toContain("Объявление снято с публикации");
    expect(mocks.notFound).not.toHaveBeenCalled();
  });

  it("marks a detail page as saved when the signed-in user already favorited it", async () => {
    mocks.listing.mockResolvedValueOnce({ listing: {
      id: "listing-1", slug: "listing-1", status: "active",
      make: { slug: "toyota" }, model: { slug: "corolla" }
    } });
    mocks.session.mockResolvedValueOnce({ user: { id: "user-1" } });
    mocks.favorites.mockResolvedValueOnce({ items: [{ id: "listing-1" }] });

    const html = renderToStaticMarkup(await CarsBySlugPage({ params: Promise.resolve(params) }));

    expect(html).toContain('data-initial-saved="true"');
    expect(mocks.favorites).toHaveBeenCalledOnce();
  });

  it("keys the detail component by listing ID so client navigation resets its state", async () => {
    const listing = (id: string) => ({
      id, slug: id, status: "active",
      make: { slug: "toyota" }, model: { slug: "corolla" }
    });
    mocks.listing.mockResolvedValueOnce({ listing: listing("listing-1") })
      .mockResolvedValueOnce({ listing: listing("listing-2") });

    const first = await CarsBySlugPage({ params: Promise.resolve(params) });
    const second = await CarsBySlugPage({ params: Promise.resolve({ slug: ["toyota", "corolla", "listing-2"] }) });

    expect((first as ReactElement).key).toBe("listing-1");
    expect((second as ReactElement).key).toBe("listing-2");
  });
});

describe("catalog route resolution", () => {
  it("resolves a model slug into exact make and model filters", async () => {
    const make = { id: "make-1", slug: "toyota", name: "Toyota" };
    const model = { id: "model-1", slug: "corolla", name: "Corolla", make_id: make.id };
    mocks.catalog.mockResolvedValueOnce({ items: [make] }).mockResolvedValueOnce({ items: [model] });

    const page = await CarsBySlugPage({ params: Promise.resolve({ slug: ["toyota", "corolla"] }) });
    const route = (page as ReactElement<{ children: ReactElement<{ search: object; title: string }> }>).props.children;

    expect(mocks.catalog).toHaveBeenNthCalledWith(1, "makes", { q: "toyota", category_code: "cars" });
    expect(mocks.catalog).toHaveBeenNthCalledWith(2, "models", { make_id: "make-1", category_code: "cars" });
    expect(route.props).toMatchObject({ search: { make_id: "make-1", model_id: "model-1", page_size: "25" }, title: "Продажа Toyota Corolla" });
  });

  it("does not turn an unknown model slug into a make-only search", async () => {
    mocks.catalog.mockResolvedValueOnce({ items: [{ id: "make-1", slug: "toyota", name: "Toyota" }] }).mockResolvedValueOnce({ items: [] });

    await expect(CarsBySlugPage({ params: Promise.resolve({ slug: ["toyota", "unknown"] }) })).rejects.toThrow("NEXT_NOT_FOUND");
  });
});

describe("category metadata thresholds", () => {
  const make = { id: "make-1", slug: "toyota", name: "Toyota" };
  const model = { id: "model-1", slug: "corolla", name: "Corolla", make_id: make.id };
  const count = (total: number) => ({ items: [], pagination: { page: 1, page_size: 1, total, pages: total } });
  const closedRobots = {
    index: false,
    follow: true,
    noarchive: true,
    googleBot: { index: false, follow: true, noimageindex: true },
  };

  it("keeps a make indexable at exactly three active offers", async () => {
    mocks.catalog.mockResolvedValueOnce({ items: [make] });
    mocks.listings.mockResolvedValueOnce(count(3));

    const metadata = await generateMetadata({ params: Promise.resolve({ slug: ["toyota"] }) });

    expect(metadata.robots).toBeUndefined();
    expect(metadata.alternates?.canonical).toBe("https://xn--80aeylebmo7f.xn--90ais/cars/toyota");
    expect(mocks.listings).toHaveBeenCalledWith({ make_id: make.id, page_size: "1" });
  });

  it("noindexes unnamed catalog entries even when they have enough offers", async () => {
    mocks.catalog.mockResolvedValueOnce({ items: [{ ...make, name: " " }] });
    mocks.listings.mockResolvedValueOnce(count(3));
    const metadata = await generateMetadata({ params: Promise.resolve({ slug: ["toyota"] }) });
    expect(metadata.robots).toEqual(closedRobots);
  });

  it("keeps real Cyrillic catalog brands indexable", async () => {
    const gaz = { ...make, slug: "cur-unicode-9ce7a3a923", name: "ГАЗ" };
    mocks.catalog.mockResolvedValueOnce({ items: [gaz] });
    mocks.listings.mockResolvedValueOnce(count(3));
    const metadata = await generateMetadata({ params: Promise.resolve({ slug: [gaz.slug] }) });
    expect(metadata.robots).toBeUndefined();
  });

  it("noindexes a make below three offers", async () => {
    mocks.catalog.mockResolvedValueOnce({ items: [make] });
    mocks.listings.mockResolvedValueOnce(count(2));

    const metadata = await generateMetadata({ params: Promise.resolve({ slug: ["toyota"] }) });

    expect(metadata.robots).toEqual(closedRobots);
  });

  it("uses the model-specific count and noindexes a model below three offers", async () => {
    mocks.catalog.mockResolvedValueOnce({ items: [make] }).mockResolvedValueOnce({ items: [model] });
    mocks.listings.mockResolvedValueOnce(count(2));

    const metadata = await generateMetadata({ params: Promise.resolve({ slug: ["toyota", "corolla"] }) });

    expect(mocks.listings).toHaveBeenCalledWith({ make_id: make.id, model_id: model.id, page_size: "1" });
    expect(metadata.robots).toEqual(closedRobots);
  });

  it("keeps a model indexable at exactly three active offers", async () => {
    mocks.catalog.mockResolvedValueOnce({ items: [make] }).mockResolvedValueOnce({ items: [model] });
    mocks.listings.mockResolvedValueOnce(count(3));

    const metadata = await generateMetadata({ params: Promise.resolve({ slug: ["toyota", "corolla"] }) });

    expect(metadata.robots).toBeUndefined();
    expect(metadata.alternates?.canonical).toBe("https://xn--80aeylebmo7f.xn--90ais/cars/toyota/corolla");
  });

  it("fails closed when a category count is missing or the API is unavailable", async () => {
    mocks.catalog.mockResolvedValueOnce({ items: [make] }).mockResolvedValueOnce({ items: [make] });
    mocks.listings.mockResolvedValueOnce({ items: [] });
    mocks.listings.mockRejectedValueOnce(new Error("offline"));

    const missingCount = await generateMetadata({ params: Promise.resolve({ slug: ["toyota"] }) });
    const unavailableCount = await generateMetadata({ params: Promise.resolve({ slug: ["toyota"] }) });

    expect(missingCount.robots).toEqual(closedRobots);
    expect(unavailableCount.robots).toEqual(closedRobots);
  });
});

describe("archived listings", () => {
  const make = { id: "make-1", slug: "toyota", name: "Toyota" };
  const model = { id: "model-1", slug: "corolla", name: "Corolla" };
  const archived = { id: "listing-1", slug: "listing-1", status: "archived", make, model };
  const similar = (count: number) => ({ items: Array.from({ length: count }, (_, index) => ({ id: `similar-${index}` })) });

  it("noindexes an archived listing while keeping its links followable", async () => {
    mocks.listing.mockResolvedValueOnce({ listing: archived });

    const metadata = await generateMetadata({ params: Promise.resolve(params) });

    expect(metadata.robots).toEqual({ index: false, follow: true });
  });

  it("noindexes a 410 listing while keeping its links followable", async () => {
    mocks.listing.mockRejectedValueOnce(new ApiClientError(410, { code: "gone", message: "Снято" }));

    const metadata = await generateMetadata({ params: Promise.resolve(params) });

    expect(metadata.robots).toEqual({ index: false, follow: true });
  });

  it("offers up to six active listings of the same model instead of the archived one", async () => {
    mocks.listing.mockResolvedValueOnce({ listing: archived });
    mocks.listings.mockResolvedValueOnce({ items: [{ id: "listing-1" }, ...similar(6).items] });

    const html = renderToStaticMarkup(await CarsBySlugPage({ params: Promise.resolve(params) }));

    expect(mocks.listings).toHaveBeenCalledWith({ make_id: "make-1", model_id: "model-1", page_size: "6" });
    expect(html).toContain("Объявление снято с публикации");
    expect(html).toContain("Похожие Toyota Corolla");
    expect(html).not.toContain('data-similar="listing-1"');
    expect(html.match(/data-similar=/g)).toHaveLength(6);
  });

  it("resolves make and model from the URL for a 410 response", async () => {
    mocks.listing.mockRejectedValueOnce(new ApiClientError(410, { code: "gone", message: "Снято" }));
    mocks.catalog.mockResolvedValueOnce({ items: [make] }).mockResolvedValueOnce({ items: [model] });
    mocks.listings.mockResolvedValueOnce(similar(2));

    const html = renderToStaticMarkup(await CarsBySlugPage({ params: Promise.resolve(params) }));

    expect(mocks.listings).toHaveBeenCalledWith({ make_id: "make-1", model_id: "model-1", page_size: "6" });
    expect(html).toContain("Похожие Toyota Corolla");
    expect(html.match(/data-similar=/g)).toHaveLength(2);
  });

  it("keeps the gone state when similar listings are unavailable", async () => {
    mocks.listing.mockResolvedValueOnce({ listing: archived });
    mocks.listings.mockRejectedValueOnce(new ApiClientError(503, { message: "Недоступно" }));

    const html = renderToStaticMarkup(await CarsBySlugPage({ params: Promise.resolve(params) }));

    expect(html).toContain("Объявление снято с публикации");
    expect(html).not.toContain("Похожие");
  });

  it("hides the block when the model has no other active offers", async () => {
    mocks.listing.mockResolvedValueOnce({ listing: archived });
    mocks.listings.mockResolvedValueOnce({ items: [{ id: "listing-1" }] });

    const html = renderToStaticMarkup(await CarsBySlugPage({ params: Promise.resolve(params) }));

    expect(html).not.toContain("Похожие");
  });
});

describe("listing detail extras", () => {
  const active = { id: "listing-1", slug: "listing-1", status: "active", make: { slug: "toyota" }, model: { slug: "corolla" } };

  it("requests related listings without waiting for the session lookup", async () => {
    let resolveSession: (value: null) => void = () => {};
    mocks.listing.mockResolvedValueOnce({ listing: active });
    mocks.session.mockReturnValueOnce(new Promise((resolve) => { resolveSession = resolve; }));

    const pending = CarsBySlugPage({ params: Promise.resolve(params) });
    await vi.waitFor(() => expect(mocks.relatedListings).toHaveBeenCalledWith("listing-1"));
    resolveSession(null);
    const html = renderToStaticMarkup(await pending);

    expect(html).toContain('data-initial-saved="false"');
  });

  it("keeps the detail page when session, favorites and related listings fail", async () => {
    mocks.listing.mockResolvedValueOnce({ listing: active });
    mocks.session.mockRejectedValueOnce(new Error("offline"));
    mocks.relatedListings.mockRejectedValueOnce(new Error("offline"));

    const html = renderToStaticMarkup(await CarsBySlugPage({ params: Promise.resolve(params) }));

    expect(html).toContain('data-initial-saved="false"');
  });
});
