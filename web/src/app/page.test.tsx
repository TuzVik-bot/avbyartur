import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ListingSummary } from "@/lib/types";

const mocks = vi.hoisted(() => ({
  listings: vi.fn(),
  catalog: vi.fn(),
  regions: vi.fn(),
  dealers: vi.fn(),
  publicStats: vi.fn(),
  getSavedListingIds: vi.fn(async () => [] as string[])
}));

vi.mock("@/lib/server-api", () => ({
  serverApi: { listings: mocks.listings, catalog: mocks.catalog, regions: mocks.regions, dealers: mocks.dealers, publicStats: mocks.publicStats },
  getSavedListingIds: mocks.getSavedListingIds
}));
vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a>
}));
vi.mock("next/image", () => ({
  default: ({ fill: _fill, sizes: _sizes, priority: _priority, ...props }: React.ImgHTMLAttributes<HTMLImageElement> & { fill?: boolean; sizes?: string; priority?: boolean }) => <img {...props} />
}));
vi.mock("@/components/listing-card", () => ({
  ListingCard: ({ listing, saved = false }: { listing: ListingSummary; saved?: boolean }) => <div data-listing-id={listing.id} data-favorite-saved={String(saved)} />
}));

import HomePage, { metadata } from "./page";

const listing: ListingSummary = {
  id: "listing-1",
  slug: "listing-1",
  title: "Марка Модель",
  make: { id: "make-1", slug: "marka", name: "Марка" },
  model: { id: "model-1", slug: "model", name: "Модель" },
  year: 2020,
  mileage_km: 50000,
  fuel: "petrol",
  transmission: "manual",
  drive: "front",
  price: { amount: "10000", currency: "BYN" },
  region: { id: "region-1", slug: "region", name: "Область" },
  city: { id: "city-1", slug: "minsk", name: "Минск" },
  seller: { id: "seller-1", type: "private", name: "Продавец" },
  created_at: "2026-09-27T00:00:00Z",
  updated_at: "2026-09-27T00:00:00Z",
  damaged: false,
  parts_only: false
};

beforeEach(() => {
  mocks.listings.mockResolvedValue({ items: [listing], fx: { rate_date: "2026-10-04", usd_rate: "3.0", scale: 1 } });
  mocks.catalog.mockResolvedValue({ items: [] });
  mocks.regions.mockResolvedValue({ items: [] });
  mocks.dealers.mockResolvedValue({ items: [] });
  mocks.publicStats.mockResolvedValue({ active_listings: 0, approved_companies: 0 });
  mocks.getSavedListingIds.mockResolvedValue([]);
});

describe("home listing cards", () => {
  it("opens the make directory from both all-makes links", async () => {
    mocks.catalog.mockResolvedValue({ items: [{ id: "make-1", slug: "bmw", name: "BMW" }] });
    const container = document.createElement("div");
    container.innerHTML = renderToStaticMarkup(await HomePage());
    const links = Array.from(container.querySelectorAll("a")).filter((link) => link.textContent?.includes("Все марки"));
    expect(links).toHaveLength(2);
    expect(links.map((link) => link.getAttribute("href"))).toEqual(["/makes", "/makes"]);
  });

  it("keeps the Russian canonical URL and declares its locale alternate", () => {
    expect(metadata.alternates).toEqual({
      canonical: "https://suite-s1.denjik.by/",
      languages: { ru: "https://suite-s1.denjik.by/" }
    });
  });

  it("marks saved listings as favorites", async () => {
    mocks.getSavedListingIds.mockResolvedValueOnce([listing.id]);

    const html = renderToStaticMarkup(await HomePage());

    expect(html).toContain('data-favorite-saved="true"');
  });

  it("keeps the agreed home heading and offers a real sell path when the catalogue is empty", async () => {
    mocks.listings.mockResolvedValueOnce({ items: [] });

    const html = renderToStaticMarkup(await HomePage());

    expect(html).toContain("Купить автомобиль");
    expect(html).toContain('href="/sell"');
    expect(html).toContain("Подать объявление");
  });

  it("searches the real make and model catalog and uses query-backed home collections", async () => {
    const html = renderToStaticMarkup(await HomePage());

    expect(html).toContain('name="make_id"');
    expect(html).toContain('name="model_id"');
    expect(html).toContain('name="price_max"');
    expect(html).toContain('href="/cars?condition=new"');
    expect(html).toContain('href="/cars?condition=used"');
    expect(html).toContain("Марки автомобилей");
    expect(html).not.toContain("Часто ищут:");
  });

  it("disables the home price filter when the listings response has no confirmed exchange rate", async () => {
    mocks.listings.mockResolvedValueOnce({ items: [listing], fx: null });

    const html = renderToStaticMarkup(await HomePage());

    expect(html).toMatch(/<input(?=[^>]*name="price_max")(?=[^>]*disabled=)[^>]*>/);
    expect(html).toContain("нет подтверждённого курса НБРБ за последние 72 часа");
  });

  it("keeps the home price filter disabled when the initial listings request fails", async () => {
    mocks.listings.mockRejectedValueOnce(new Error("temporary catalog failure"));

    const html = renderToStaticMarkup(await HomePage());

    expect(html).toMatch(/<input(?=[^>]*name="price_max")(?=[^>]*disabled=)[^>]*>/);
    expect(html).toContain("нет подтверждённого курса НБРБ за последние 72 часа");
    expect(html).toContain("Каталог временно недоступен");
  });

  it("describes seller contacts without promising public phone reveal", async () => {
    const html = renderToStaticMarkup(await HomePage());

    expect(html).toContain("Контакты не показываются в публичной выдаче");
    expect(html).not.toContain("Телефон показывается посетителю по запросу");
  });

  it("shows public counts from the aggregate endpoint and explains moderation", async () => {
    mocks.publicStats.mockResolvedValueOnce({ active_listings: 27, approved_companies: 4 });

    const html = renderToStaticMarkup(await HomePage());
    const rendered = new DOMParser().parseFromString(html, "text/html");

    expect(rendered.querySelector('[aria-label="Состояние авторынка"]')?.textContent).toContain("Активных объявлений: 27");
    expect(rendered.querySelector('[aria-label="Состояние авторынка"]')?.textContent).toContain("Допущенные компании: 4");
    const status = rendered.querySelector('[aria-label="Состояние авторынка"]')?.textContent || "";
    expect(status).toContain("проверяются обязательные поля карточки, их согласованность и минимум обработанных фото");
    expect(status).toContain("подсказки о повторах и необычно низкой цене");
    expect(status).toContain("это не автоматическое решение");
    expect(status).not.toContain("проверяем VIN или историю автомобиля");
  });

  it("renders aggregate failures as unavailable, never as a zero market", async () => {
    mocks.publicStats.mockRejectedValueOnce(new Error("aggregate unavailable"));

    const html = renderToStaticMarkup(await HomePage());
    const rendered = new DOMParser().parseFromString(html, "text/html");

    expect(rendered.querySelector('[aria-label="Состояние авторынка"]')?.textContent).toContain("Статистика временно недоступна");
    expect(rendered.querySelector('[aria-label="Состояние авторынка"]')?.textContent).not.toContain("Активных объявлений: 0");
  });
});
