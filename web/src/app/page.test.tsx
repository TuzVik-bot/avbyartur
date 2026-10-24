import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ListingSummary } from "@/lib/types";

const mocks = vi.hoisted(() => ({
  listings: vi.fn(),
  catalog: vi.fn(),
  regions: vi.fn(),
  dealers: vi.fn(),
  getSavedListingIds: vi.fn(async () => [] as string[])
}));

vi.mock("@/lib/server-api", () => ({
  serverApi: { listings: mocks.listings, catalog: mocks.catalog, regions: mocks.regions, dealers: mocks.dealers },
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
  mocks.getSavedListingIds.mockResolvedValue([]);
});

describe("home listing cards", () => {
  it("requests eight recent listings without fabricated market statistics", async () => {
    const html = renderToStaticMarkup(await HomePage());
    expect(mocks.listings).toHaveBeenCalledWith({ page_size: "8", sort: "newest" });
    expect(html).not.toContain("Активных объявлений");
  });

  it("offers truthful purchase shortcuts and reuses the existing family selection", async () => {
    const container = document.createElement("div");
    container.innerHTML = renderToStaticMarkup(await HomePage());

    expect(container.querySelector("h1")?.textContent).toBe("Найдите автомобиль по своим условиям");
    const quickLinks = Array.from(container.querySelector("nav[aria-label='Быстрые сценарии покупки']")?.querySelectorAll("a") || []);
    expect(quickLinks.map((link) => [link.getAttribute("href"), link.textContent])).toEqual([
      ["/cars?category_code=cars&price_max=30000&currency=BYN", expect.stringContaining("До 30 000 BYN")],
      ["/cars?category_code=cars&fuel=electric", expect.stringContaining("Электромобили")],
      ["/cars/city/minsk", expect.stringContaining("В Минске")],
      ["/useful-information#use-case-presets-title", expect.stringContaining("Семейный автомобиль")]
    ]);
  });

  it("keeps every advertisement category and usable services without empty ad placeholders", async () => {
    const html = renderToStaticMarkup(await HomePage());
    for (const path of ["/motorcycles", "/trucks", "/parts", "/services", "/customs-calculator", "/dealers", "/partner"]) {
      expect(html).toContain(`href="${path}"`);
    }
    expect(html).not.toContain("Здесь может быть");
    expect(html.match(/<img/g)).toHaveLength(1);
  });

  it("offers one make directory without duplicating the make list", async () => {
    mocks.catalog.mockResolvedValue({ items: [{ id: "make-1", slug: "bmw", name: "BMW" }] });
    const container = document.createElement("div");
    container.innerHTML = renderToStaticMarkup(await HomePage());
    const links = Array.from(container.querySelectorAll("a")).filter((link) => link.textContent?.includes("Все марки"));
    expect(links).toHaveLength(1);
    expect(links.map((link) => link.getAttribute("href"))).toEqual(["/makes"]);
  });

  it("shows the approved popular makes with catalog-backed slugs", async () => {
    const names = ["Audi", "BMW", "Buick", "Chevrolet", "Chrysler", "Citroen", "Dodge", "Fiat", "Ford", "Geely", "GMC", "Honda", "Hyundai", "Kia", "Lada", "Land Rover", "Lexus", "Mazda", "Mercedes-Benz", "Mitsubishi", "Nissan", "Opel", "Peugeot", "Renault", "Skoda", "Subaru", "Tesla", "Toyota", "Volkswagen", "Volvo"];
    mocks.catalog.mockResolvedValue({ items: names.map((name) => ({ id: name, name, slug: name.toLowerCase().replaceAll(" ", "-") })) });

    const container = document.createElement("div");
    container.innerHTML = renderToStaticMarkup(await HomePage());
    const list = container.querySelector("nav[aria-label='Быстрый поиск по марке'] ul");
    const links = Array.from(list?.querySelectorAll("a") || []);

    expect(links.map((link) => link.textContent)).toEqual(names);
    expect(links.map((link) => link.getAttribute("href"))).toEqual(names.map((name) => `/cars/${encodeURIComponent(name.toLowerCase().replaceAll(" ", "-"))}`));
  });

  it("keeps all 30 popular names when the catalog is partial and uses only real catalog aliases", async () => {
    mocks.catalog.mockResolvedValue({ items: [
      { id: "citroen", name: "Citroën", slug: "citroen" },
      { id: "kia", name: "Kia Motors", slug: "kia" },
      { id: "geely", name: "Geely Holding", slug: "geely" }
    ] });

    const container = document.createElement("div");
    container.innerHTML = renderToStaticMarkup(await HomePage());
    const links = Array.from(container.querySelector("nav[aria-label='Быстрый поиск по марке'] ul")?.querySelectorAll("a") || []);
    const hrefByName = new Map(links.map((link) => [link.textContent, link.getAttribute("href")]));

    expect(links).toHaveLength(30);
    expect(hrefByName.get("Citroen")).toBe("/cars/citroen");
    expect(hrefByName.get("Kia")).toBe("/cars/kia");
    expect(hrefByName.get("Geely")).toBe("/cars/geely");
    expect(hrefByName.get("Buick")).toBe("/cars?q=Buick");
    expect(hrefByName.get("Tesla")).toBe("/cars?q=Tesla");
    expect(hrefByName.get("Lada")).toBe("/cars?q=Lada");
  });

  it("marks ad placements and routes every advertising CTA to the existing partner page", async () => {
    const container = document.createElement("div");
    container.innerHTML = renderToStaticMarkup(await HomePage());
    const advertising = container.querySelectorAll("aside[aria-label='Реклама']");
    const partnerSection = container.querySelector("section[aria-labelledby='home-partners-heading']");

    expect(advertising).toHaveLength(2);
    expect(partnerSection?.querySelectorAll("article")).toHaveLength(3);
    expect(partnerSection?.textContent).toContain("Шины и диски");
    expect(partnerSection?.textContent).toContain("Страхование автомобиля");
    expect(partnerSection?.textContent).toContain("Автосервис и обслуживание");
    for (const cta of Array.from(container.querySelectorAll("a")).filter((link) => link.textContent?.includes("Разместить рекламу"))) {
      expect(cta.getAttribute("href")).toBe("/partner");
    }
    expect(container.textContent).not.toContain("активных покупателей");
  });

  it("keeps the Russian canonical URL and declares its locale alternate", () => {
    expect(metadata.alternates).toEqual({
      canonical: "https://xn--80aeylebmo7f.xn--90ais/",
      languages: { ru: "https://xn--80aeylebmo7f.xn--90ais/" }
    });
  });

  it("marks saved listings as favorites", async () => {
    mocks.getSavedListingIds.mockResolvedValueOnce([listing.id]);

    const html = renderToStaticMarkup(await HomePage());

    expect(html).toContain('data-favorite-saved="true"');
  });

  it("explains a real empty catalogue and offers search paths without sample listings", async () => {
    mocks.listings.mockResolvedValueOnce({ items: [] });

    const container = document.createElement("div");
    container.innerHTML = renderToStaticMarkup(await HomePage());

    expect(container.textContent).toContain("Новых объявлений пока нет");
    expect(container.textContent).toContain("пока нет опубликованных предложений");
    expect(Array.from(container.querySelectorAll("a[href='/useful-information#use-case-presets-title']")).find((link) => link.textContent?.includes("Подборки по задаче"))?.textContent).toContain("Подборки по задаче");
    expect(container.querySelector("a[href='/sell']")?.textContent).toContain("Подать объявление");
    expect(container.querySelectorAll("[data-listing-id]")).toHaveLength(0);
  });

  it("keeps the API failure state separate from the confirmed empty catalogue", async () => {
    mocks.listings.mockRejectedValueOnce(new Error("temporary catalog failure"));

    const container = document.createElement("div");
    container.innerHTML = renderToStaticMarkup(await HomePage());

    expect(container.textContent).toContain("Сейчас не удаётся загрузить объявления");
    expect(container.textContent).not.toContain("Новых объявлений пока нет");
    expect(container.textContent).toContain("не подтвердил, есть ли сейчас опубликованные предложения");
  });

  it("does not invent market statistics when the catalog has no counts", async () => {
    const html = renderToStaticMarkup(await HomePage());

    expect(html).not.toContain("Активных объявлений");
    expect(html).not.toContain("Состояние авторынка");
    expect(html).toContain("Поиск по опубликованным объявлениям Беларуси");
  });

  it("searches the real make and model catalog and uses query-backed home collections", async () => {
    const html = renderToStaticMarkup(await HomePage());

    expect(html).toContain('name="make_id"');
    expect(html).toContain('name="model_id"');
    expect(html).toContain('name="price_max"');
    expect(html).toContain('href="/cars?condition=new"');
    expect(html).toContain('href="/cars?condition=used"');
    expect(html).toContain("Популярные марки");
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
});
