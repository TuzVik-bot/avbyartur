import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ListingCard } from "@/components/listing-card";
import { api } from "@/lib/api";
import type { ListingSummary } from "@/lib/types";

const mocks = vi.hoisted(() => ({
  user: null as null | { id: string },
  push: vi.fn(),
  refresh: vi.fn()
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a>
}));
vi.mock("next/image", () => ({
  default: ({ unoptimized: _unoptimized, priority: _priority, ...props }: React.ImgHTMLAttributes<HTMLImageElement> & { unoptimized?: boolean; priority?: boolean }) => <img {...props} />
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push, refresh: mocks.refresh }) }));
vi.mock("@/components/auth-provider", () => ({ useAuth: () => ({ user: mocks.user }) }));
vi.mock("@/components/comparison/comparison-action", () => ({ ComparisonAction: ({ listingId }: { listingId: string }) => <button data-compare-listing={listingId}>Добавить к сравнению</button> }));

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  mocks.user = null;
  mocks.push.mockReset();
  mocks.refresh.mockReset();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

function listing(overrides: Partial<ListingSummary & { published_at?: string | null; engine_volume_l?: string | number | null; power_hp?: number | null }> = {}): ListingSummary {
  return {
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
    parts_only: false,
    ...overrides
  };
}

describe("listing card city navigation", () => {
  it("offers comparison for the current listing", () => {
    act(() => root.render(createElement(ListingCard, { listing: listing() })));
    expect(container.querySelector('[data-compare-listing="listing-1"]')?.textContent).toBe("Добавить к сравнению");
  });

  it("links catalog locations to the planned city route", () => {
    act(() => root.render(createElement(ListingCard, { listing: listing() })));

    expect(container.querySelector('a[href="/cars/city/minsk"]')?.textContent).toBe("Минск");
  });

  it("keeps manually entered locations as text", () => {
    act(() => root.render(createElement(ListingCard, { listing: listing({ city: null, manual_city: "Жлобин" }) })));

    expect(container.querySelector(".card-footer")?.textContent).toContain("Жлобин");
    expect(container.querySelector('.card-footer a[href^="/cars/city/"]')).toBeNull();
  });

  it("shows a visible, announced message if saving a favorite fails", async () => {
    mocks.user = { id: "user-1" };
    vi.spyOn(api, "addFavorite").mockRejectedValueOnce(new Error("Временно недоступно"));
    act(() => root.render(createElement(ListingCard, { listing: listing() })));

    await act(async () => {
      container.querySelector<HTMLButtonElement>(".favorite-button")!.click();
    });

    expect(container.querySelector('[role="alert"]')?.textContent).toBe("Временно недоступно");
    expect(container.querySelector(".favorite-error")?.classList.contains("sr-only")).toBe(false);
  });
});

describe("listing card photos", () => {
  it("uses responsive source sizes for grid and row layouts", () => {
    act(() => root.render(createElement(ListingCard, { listing: listing() })));
    expect(container.querySelector("img")?.getAttribute("sizes")).toContain("(max-width: 520px)");
    expect(container.querySelector("img")?.getAttribute("sizes")).toContain("(max-width: 1020px)");

    act(() => root.render(createElement(ListingCard, { listing: listing(), variant: "row" })));
    expect(container.querySelector("img")?.getAttribute("sizes")).toBe("(max-width: 520px) 118px, 220px");
  });

  it("uses the first public photo URL and omits the synthetic treatment", () => {
    act(() => root.render(createElement(ListingCard, { listing: listing({
      photo_urls: ["/api/v1/photos/first/768", "/api/v1/photos/second/768"],
      cover_url: "/legacy-cover.jpg"
    }) })));

    const image = container.querySelector("img");
    expect(image?.getAttribute("src")).toBe("/api/v1/photos/first/768");
    expect(image?.getAttribute("alt")).toBe("Фотография: Марка Модель");
    expect(container.querySelector(".synthetic-label")).toBeNull();
  });

  it("uses cover_url when no public photo URL is available", () => {
    act(() => root.render(createElement(ListingCard, { listing: listing({ photo_urls: [], cover_url: "/legacy-cover.jpg" }) })));

    const image = container.querySelector("img");
    expect(image?.getAttribute("src")).toBe("/legacy-cover.jpg");
    expect(image?.getAttribute("alt")).toBe("Фотография: Марка Модель");
    expect(container.querySelector(".synthetic-label")).toBeNull();
  });

  it("shows the synthetic fallback when neither photo source exists", () => {
    act(() => root.render(createElement(ListingCard, { listing: listing({ photo_urls: [], cover_url: null }) })));

    const image = container.querySelector("img");
    expect(image?.getAttribute("src")).toBe("/vehicles/silver-wagon.png");
    expect(image?.getAttribute("alt")).toBe("Синтетическое изображение для объявления «Марка Модель»");
    expect(container.querySelector(".synthetic-label")?.textContent).toBe("Синтетическое фото");
  });
});

describe("listing card facts", () => {
  it("shows an active urgent promotion badge", () => {
    act(() => root.render(createElement(ListingCard, { listing: { ...listing(), promotion_badges: ["urgent"] } as ListingSummary })));

    expect(container.querySelector("[data-urgent-badge]")?.textContent).toBe("Срочно");
  });

  it("shows only supplied specs and reports Minsk publication age and market comparison source", () => {
    vi.setSystemTime(new Date("2026-10-09T21:30:00.000Z"));
    const detailed = {
      ...listing({ published_at: "2026-10-09T21:30:00.000Z", engine_volume_l: "1.6", power_hp: 120 }),
      price: {
        amount: "10000",
        currency: "BYN" as const,
        market_comparison: {
          label: "below_market" as const,
          median_byn: "12000",
          sample_size: 14,
          seller_count: 9,
          as_of: "2026-10-08",
          rate_date: null
        }
      }
    };
    act(() => root.render(createElement(ListingCard, { listing: detailed })));

    expect(container.textContent).toContain("1,6 л");
    expect(container.textContent).toContain("120 л.с.");
    expect(container.textContent).toContain("Бензин");
    expect(container.textContent).toContain("Механика");
    expect(container.textContent).toContain("Опубликовано сегодня");
    const marketBadge = container.querySelector<HTMLElement>("[data-market-comparison]");
    expect(marketBadge?.textContent).toContain("Цена ниже рынка");
    expect(marketBadge?.title).toContain("По предложениям Авторынка");
    expect(marketBadge?.title).toContain("14 объявлениям");
    expect(marketBadge?.title).toContain("08.10.2026");
    const specs = Array.from(container.querySelectorAll(".card-specs > span"), (element) => element.textContent ?? "");
    expect(specs).toHaveLength(6);
    expect(specs[0]).toBe("2020 г.");
    expect(specs[1]).toContain("км");
    expect(specs[2]).toBe("1,6 л");
    expect(specs[3]).toBe("120 л.с.");
    expect(container.querySelector('.card-footer a[href="/cars/city/minsk"]')?.textContent).toBe("Минск");
    expect(container.querySelector(".card-published")?.textContent).toBe("Опубликовано сегодня");

    const withoutAge = listing({ created_at: "2026-10-09T21:30:00.000Z" });
    act(() => root.render(createElement(ListingCard, { listing: withoutAge })));
    expect(container.textContent).not.toContain("Опубликовано");
    expect(container.textContent).not.toContain("л.с.");
    expect(container.querySelector("[data-market-comparison]")).toBeNull();

    act(() => root.render(createElement(ListingCard, { listing: listing({ published_at: "2026-10-07T21:30:00.000Z" }) })));
    expect(container.textContent).toContain("Опубликовано 2 дня назад");
    vi.useRealTimers();
  });

  it("does not invent missing facts or show combustion volume for an electric car", () => {
    act(() => root.render(createElement(ListingCard, { listing: listing({
      year: null,
      mileage_km: null,
      engine_volume_l: null,
      power_hp: null,
      fuel: null,
      transmission: null,
      city: null,
      manual_city: null,
      published_at: null
    }) })));

    const specs = Array.from(container.querySelectorAll(".card-specs > span"), (element) => element.textContent ?? "");
    expect(specs).toContain("Год не указан");
    expect(specs).toContain("Пробег не указан");
    expect(specs.filter((value) => value === "Не указан")).toHaveLength(2);
    expect(specs.some((value) => value.includes("л.с."))).toBe(false);
    expect(specs.some((value) => value.includes(" л"))).toBe(false);
    expect(container.querySelector(".card-published")).toBeNull();
    expect(container.querySelector(".card-footer")?.textContent).toContain("Населённый пункт не указан");

    act(() => root.render(createElement(ListingCard, { listing: listing({ engine_volume_l: " " }) })));
    expect(container.querySelector(".card-specs")?.textContent).not.toContain("0 л");

    act(() => root.render(createElement(ListingCard, { listing: listing({ fuel: "electric", engine_volume_l: "1.6", power_hp: 125 }) })));
    expect(container.querySelector(".card-specs")?.textContent).not.toContain("1,6 л");
    expect(container.querySelector(".card-specs")?.textContent).toContain("125 л.с.");
  });

  it("uses Minsk calendar days and omits a future publication date", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-09T20:59:00.000Z"));
    const publishedAt = "2026-10-09T20:58:00.000Z";
    act(() => root.render(createElement(ListingCard, { listing: listing({ published_at: publishedAt }) })));
    expect(container.querySelector(".card-published")?.textContent).toBe("Опубликовано сегодня");

    vi.setSystemTime(new Date("2026-10-09T21:01:00.000Z"));
    act(() => root.render(createElement(ListingCard, { listing: listing({ published_at: publishedAt }) })));
    expect(container.querySelector(".card-published")?.textContent).toBe("Опубликовано вчера");

    act(() => root.render(createElement(ListingCard, { listing: listing({ published_at: "2026-10-10T22:00:00.000Z" }) })));
    expect(container.querySelector(".card-published")).toBeNull();
  });
});

describe("favorite removal", () => {
  it("refreshes the saved list after a favorite is removed", async () => {
    mocks.user = { id: "user-1" };
    const removeFavorite = vi.spyOn(api, "removeFavorite").mockResolvedValue({ ok: true });
    act(() => root.render(createElement(ListingCard, { listing: listing(), saved: true })));
    const button = container.querySelector<HTMLButtonElement>(".favorite-button")!;

    await act(async () => { button.click(); });

    expect(removeFavorite).toHaveBeenCalledWith("listing-1");
    expect(button.getAttribute("aria-pressed")).toBe("false");
    expect(mocks.refresh).toHaveBeenCalledOnce();
  });
});


describe("photo labels", () => {
  it("shows assigned labels over real photos in grid and row layouts", () => {
    const labelled = listing({ photo_urls: ["/car.jpg"], photo_badges: ["verified", "free_history", "best_price"] });
    for (const variant of ["grid", "row"] as const) {
      act(() => root.render(createElement(ListingCard, { listing: labelled, variant })));
      const overlay = container.querySelector(".listing-card-media .listing-photo-badges");
      expect(overlay?.textContent).toContain("Проверено Авторынок");
      expect(overlay?.textContent).toContain("История бесплатно");
      expect(overlay?.textContent).toContain("Лучшая цена");
      expect(overlay?.querySelectorAll(".listing-photo-badge")).toHaveLength(3);
    }
  });

  it("does not show labels on the synthetic fallback", () => {
    act(() => root.render(createElement(ListingCard, { listing: listing({ photo_badges: ["verified"] }) })));
    expect(container.querySelector(".listing-photo-badges")).toBeNull();
  });
});
