import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { ListingDetail } from "@/components/listing-detail";
import { api, ApiClientError } from "@/lib/api";
import { clearComparisonIds } from "@/lib/comparison-state";
import type { Listing } from "@/lib/types";

const routerMocks = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a>
}));
vi.mock("next/image", () => ({
  default: ({ unoptimized: _unoptimized, priority: _priority, ...props }: React.ImgHTMLAttributes<HTMLImageElement> & { unoptimized?: boolean; priority?: boolean }) => <img {...props} />
}));
vi.mock("next/navigation", () => ({ useRouter: () => routerMocks }));
vi.mock("@/components/auth-provider", () => ({ useAuth: () => ({ user: null }) }));

let container: HTMLDivElement;
let root: Root;
let historyLoader: Mock<typeof api.listingPriceHistory>;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  localStorage.clear();
  clearComparisonIds();
  vi.spyOn(api, "guestContactEnabled").mockResolvedValue({ guest_contact_reveal_enabled: false });
  historyLoader = vi.spyOn(api, "listingPriceHistory").mockResolvedValue({ items: [] });
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  clearComparisonIds();
  vi.restoreAllMocks();
});

const listing: Listing = {
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
  status: "active",
  revision: 1,
  description: "Описание",
  condition: "used",
  photo_urls: []
};

describe("contact reveal", () => {
  it("shows modification and seller-provided VIN context beside the price without claiming a history check", async () => {
    await act(async () => root.render(createElement(ListingDetail, {
      listing: { ...listing, vin: "WVWZZZ1JZXW000001", updated_at: "2026-10-20T12:00:00Z" }
    })));
    const panel = container.querySelector('aside[aria-label="Цена и продавец"]');
    expect(panel?.textContent).toContain("Изменено");
    expect(panel?.querySelector("time")?.getAttribute("dateTime")).toBe("2026-10-20T12:00:00Z");
    expect(panel?.textContent).toContain("VIN указан продавцом");
    expect(panel?.textContent).toContain("История автомобиля не проверена");
    expect(panel?.textContent).not.toContain("VIN проверен");
  });

  it("does not imply a VIN report exists when the seller omitted VIN", async () => {
    await act(async () => root.render(createElement(ListingDetail, { listing: { ...listing, vin: null } })));
    const panel = container.querySelector('aside[aria-label="Цена и продавец"]');
    expect(panel?.textContent).not.toContain("VIN не указан");
    expect(panel?.textContent).not.toContain("VIN указан продавцом");
  });

  it("takes a guest to login with the new chat route as the next path", async () => {
    await act(async () => root.render(createElement(ListingDetail, { listing })));

    const link = container.querySelector<HTMLAnchorElement>(".contact-chat");
    expect(link?.textContent).toContain("Написать продавцу");
    expect(link?.getAttribute("href")).toBe(`/login?next=${encodeURIComponent(`/account/messages/new?listing_id=${listing.id}`)}`);
  });

  it("lets a guest explicitly reveal a phone only when the public capability is enabled", async () => {
    vi.spyOn(api, "guestContactEnabled").mockResolvedValue({ guest_contact_reveal_enabled: true });
    const revealPhone = vi.spyOn(api, "revealPhone").mockResolvedValue({ phone: "+375 29 000 00 00" });
    await act(async () => {
      root.render(createElement(ListingDetail, { listing }));
      await Promise.resolve();
    });

    expect(container.textContent).toContain("Телефон можно посмотреть без входа в аккаунт.");
    expect(container.textContent).not.toContain("+375 29 000 00 00");
    expect(container.querySelector<HTMLAnchorElement>(".contact-chat")?.getAttribute("href")).toBe(
      `/login?next=${encodeURIComponent(`/account/messages/new?listing_id=${listing.id}`)}`
    );
    const button = container.querySelector<HTMLButtonElement>(".contact-reveal")!;
    await act(async () => {
      button.click();
      await Promise.resolve();
    });

    expect(revealPhone).toHaveBeenCalledOnce();
    expect(container.textContent).toContain("+375 29 000 00 00");
  });

  it("keeps the disabled pilot login redirect after an unauthenticated reveal is rejected", async () => {
    vi.spyOn(api, "revealPhone").mockRejectedValue(new ApiClientError(401, { code: "unauthorized" }));
    await act(async () => root.render(createElement(ListingDetail, { listing })));

    const button = container.querySelector<HTMLButtonElement>(".contact-reveal")!;
    await act(async () => {
      button.click();
      await Promise.resolve();
    });

    expect(routerMocks.push).toHaveBeenCalledWith(
      `/login?next=${encodeURIComponent(`/cars/${listing.make!.slug}/${listing.model!.slug}/${listing.id}`)}`
    );
  });

  it("reflects the saved state supplied by the listing route", async () => {
    await act(async () => root.render(createElement(ListingDetail, { listing, initialSaved: true })));

    expect(container.querySelector<HTMLButtonElement>(".favorite-button")?.getAttribute("aria-pressed")).toBe("true");
    expect(container.querySelector<HTMLButtonElement>(".favorite-button")?.getAttribute("aria-label")).toBe("Убрать из избранного");
  });

  it("sends only one reveal request while a phone lookup is pending", async () => {
    let resolveReveal!: (value: { phone: string }) => void;
    const revealPhone = vi.spyOn(api, "revealPhone").mockImplementation(() => new Promise((resolve) => { resolveReveal = resolve; }));
    await act(async () => root.render(createElement(ListingDetail, { listing })));

    const button = container.querySelector<HTMLButtonElement>(".contact-reveal");
    expect(button).not.toBeNull();
    await act(async () => { button!.click(); });
    expect(button!.disabled).toBe(true);
    expect(button!.getAttribute("aria-busy")).toBe("true");
    await act(async () => { button!.click(); });
    expect(revealPhone).toHaveBeenCalledOnce();

    await act(async () => {
      resolveReveal({ phone: "+375 29 000 00 00" });
      await Promise.resolve();
    });
    expect(container.textContent).toContain("+375 29 000 00 00");
  });
});

describe("listing detail comparison", () => {
  it("provides add and selected-list actions on the public listing detail", async () => {
    await act(async () => root.render(createElement(ListingDetail, { listing })));
    const addButton = [...container.querySelectorAll("button")].find((button) => button.textContent?.includes("Добавить к сравнению"));

    expect(addButton).not.toBeNull();
    expect(container.querySelector('a[href="/compare"]')?.textContent).toBe("Сравнение");
    await act(async () => addButton!.click());
    expect(container.querySelector('a[href="/compare"]')?.textContent).toBe("Сравнение (1)");
  });
});

describe("public price history", () => {
  it("shows recorded dates and original currencies without substituting the current converted price", async () => {
    historyLoader.mockResolvedValue({ items: [{
      id: "price-event-1",
      event_type: "changed",
      amount: "5000.50",
      currency: "USD",
      previous_amount: "5200.00",
      previous_currency: "USD",
      recorded_at: "2026-10-15T12:00:00Z"
    }] });
    const usdListing = { ...listing, price: { amount: "5000", currency: "USD" as const, display_byn: "13500.00", rate_date: "2026-10-20" } };

    await act(async () => {
      root.render(createElement(ListingDetail, { listing: usdListing }));
      await Promise.resolve();
    });

    const history = container.querySelector<HTMLElement>("[data-testid='listing-price-history']");
    expect(historyLoader).toHaveBeenCalledWith(listing.id);
    expect(history?.textContent).toContain("5 000,5 USD");
    expect(history?.textContent).toContain("5 200 USD");
    expect(history?.textContent).not.toContain("13 500 BYN");
    expect([...history!.querySelectorAll(".sr-only")].map((label) => label.textContent)).toEqual(["Было: ", "Стало: "]);
    expect(history?.querySelector("time")?.getAttribute("datetime")).toBe("2026-10-15T12:00:00Z");
  });

  it("labels a baseline as a recorded price without implying an earlier value", async () => {
    historyLoader.mockResolvedValue({ items: [{
      id: "price-event-baseline",
      event_type: "baseline",
      amount: "4500",
      currency: "USD",
      previous_amount: null,
      previous_currency: null,
      recorded_at: "2026-10-15T12:00:00Z"
    }] });

    await act(async () => {
      root.render(createElement(ListingDetail, { listing }));
      await Promise.resolve();
    });

    const entry = container.querySelector<HTMLElement>("[data-testid='listing-price-history'] li");
    expect(entry?.querySelector("strong")?.textContent).toBe("Цена зафиксирована");
    expect(entry?.querySelector("p strong")?.textContent).toBe("4 500 USD");
    expect(entry?.querySelector(".sr-only")?.textContent).toBe("Цена: ");
    expect(entry?.textContent).not.toContain("Было:");
    expect(entry?.textContent).not.toContain(" → ");
  });

  it("distinguishes an empty history from a failed request", async () => {
    await act(async () => {
      root.render(createElement(ListingDetail, { listing }));
      await Promise.resolve();
    });
    expect(container.querySelector("[data-testid='listing-price-history']")?.textContent).toContain("Изменений цены пока нет.");

    historyLoader.mockRejectedValueOnce(new Error("offline"));
    await act(async () => {
      root.render(createElement(ListingDetail, { listing: { ...listing, id: "listing-2" } }));
      await Promise.resolve();
    });
    const history = container.querySelector("[data-testid='listing-price-history']");
    expect(history?.textContent).toContain("Не удалось загрузить историю цены.");
    expect(history?.textContent).not.toContain("Изменений цены пока нет.");
    expect(history?.querySelector('[role="alert"]')).not.toBeNull();
  });

  it("does not request or render price history for an inactive listing", async () => {
    await act(async () => root.render(createElement(ListingDetail, { listing: { ...listing, status: "paused" } })));

    expect(historyLoader).not.toHaveBeenCalled();
    expect(container.querySelector("[data-testid='listing-price-history']")).toBeNull();
  });
});

describe("catalog specifications", () => {
  it("shows the selected modification and available power in public details", async () => {
    const catalogListing: Listing = {
      ...listing,
      modification: { id: "modification-1", slug: "318i", name: "318i", generation_id: "generation-1", specs: null },
      power_hp: 180
    };
    await act(async () => root.render(createElement(ListingDetail, { listing: catalogListing })));

    const facts = container.querySelector(".detail-facts")?.textContent || "";
    expect(facts).toContain("Модификация318i");
    expect(facts).toContain("Мощность180 л.с.");
  });

  it("uses catalog power when the listing snapshot does not include it", async () => {
    const catalogListing: Listing = {
      ...listing,
      modification: {
        id: "modification-1",
        slug: "318i",
        name: "318i",
        generation_id: "generation-1",
        specs: { engine_code: null, frame_code: null, engine_l: null, power_hp: 156, fuel: null, transmission: null, drive: null, production_period_raw: null, summary_raw: null }
      },
      power_hp: null
    };
    await act(async () => root.render(createElement(ListingDetail, { listing: catalogListing })));

    expect(container.querySelector(".detail-facts")?.textContent).toContain("Мощность156 л.с.");
  });

  it("renders the complete seller-entered characteristics and related listings", async () => {
    const detailed: Listing = {
      ...listing, color: "blue", customs_status: "cleared_rb", technical_condition: "good", body_condition: "minor_damage",
      exchange: true, bargaining: true, credit: true, leasing: true, equipment: ["abs", "rear_camera"], district: "Центральный", call_hours: "9:00–20:00"
    };
    await act(async () => root.render(createElement(ListingDetail, { listing: detailed, relatedListings: [{ ...listing, id: "related-1", title: "Похожий автомобиль" }] })));

    const facts = container.querySelector(".detail-facts")?.textContent || "";
    expect(facts).toContain("Синий");
    expect(facts).toContain("Оформлен в РБ");
    expect(facts).toContain("Возможен");
    expect(facts).toContain("ABS");
    expect(facts).toContain("Центральный");
    expect(facts).toContain("9:00–20:00");
    expect(container.textContent).toContain("Похожие объявления");
    const relatedLink = container.querySelector<HTMLAnchorElement>('.related-listings .card-title[href="/cars/marka/model/related-1"]');
    expect(relatedLink?.textContent).toBe("Похожий автомобиль");
  });
});

describe("photo gallery", () => {
  it("shows every public photo and lets keyboard users change the active image", async () => {
    const galleryListing: Listing = {
      ...listing,
      photo_urls: ["/photo-1.webp", "/photo-2.webp", "/photo-3.webp", "/photo-4.webp", "/photo-5.webp", "/photo-6.webp"]
    };
    await act(async () => root.render(createElement(ListingDetail, { listing: galleryListing })));

    const gallery = container.querySelector<HTMLElement>(".detail-gallery")!;
    const thumbnails = [...container.querySelectorAll<HTMLButtonElement>(".detail-thumbnail")];
    const mainImage = () => container.querySelector<HTMLImageElement>("#detail-main-image")!;
    expect(thumbnails).toHaveLength(6);
    expect(mainImage().src).toContain("/photo-1.webp");
    expect(mainImage().alt).toBe("Фотография 1 из 6: Марка Модель");
    expect(thumbnails[0].getAttribute("aria-current")).toBe("true");

    await act(async () => { thumbnails[5].click(); });
    expect(mainImage().src).toContain("/photo-6.webp");
    expect(thumbnails[5].getAttribute("aria-current")).toBe("true");
    expect(thumbnails[0].getAttribute("aria-current")).toBeNull();

    await act(async () => { gallery.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true })); });
    expect(mainImage().src).toContain("/photo-5.webp");
    await act(async () => { gallery.dispatchEvent(new KeyboardEvent("keydown", { key: "Home", bubbles: true })); });
    expect(mainImage().src).toContain("/photo-1.webp");
    await act(async () => { gallery.dispatchEvent(new KeyboardEvent("keydown", { key: "End", bubbles: true })); });
    expect(mainImage().src).toContain("/photo-6.webp");
  });
});

describe("report submission", () => {
  it("allows the full API comment length", async () => {
    await act(async () => root.render(createElement(ListingDetail, { listing })));

    expect(container.querySelector<HTMLTextAreaElement>('.report-form textarea[name="comment"]')?.maxLength).toBe(2000);
  });

  it("offers the report categories accepted by the API", async () => {
    await act(async () => root.render(createElement(ListingDetail, { listing })));

    const values = [...container.querySelectorAll<HTMLSelectElement>('.report-form select[name="category"] option')]
      .map((option) => option.value)
      .filter(Boolean);
    expect(values).toEqual(["incorrect_info", "duplicate", "fraud", "prohibited", "other"]);
  });

  it("rejects a category that is not supported by the API", async () => {
    const createReport = vi.spyOn(api, "createReport").mockResolvedValue({ id: "report-1", status: "open" });
    await act(async () => root.render(createElement(ListingDetail, { listing })));

    const form = container.querySelector<HTMLFormElement>(".report-form form")!;
    form.querySelector<HTMLSelectElement>('select[name="category"]')!.value = "unsupported";
    await act(async () => {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await Promise.resolve();
    });

    expect(createReport).not.toHaveBeenCalled();
    expect(container.querySelector('[role="alert"]')?.textContent).toBe("Выберите причину жалобы.");
  });

  it("prevents a second report while the first submission is pending", async () => {
    let resolveReport!: (value: { id: string; status: string }) => void;
    const createReport = vi.spyOn(api, "createReport").mockImplementation(() => new Promise((resolve) => { resolveReport = resolve; }));
    await act(async () => root.render(createElement(ListingDetail, { listing })));

    const form = container.querySelector<HTMLFormElement>(".report-form form")!;
    const category = form.querySelector<HTMLSelectElement>('select[name="category"]')!;
    category.value = "incorrect_info";
    const button = form.querySelector<HTMLButtonElement>('button[type="submit"]')!;
    await act(async () => {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });

    expect(button.disabled).toBe(true);
    expect(button.getAttribute("aria-busy")).toBe("true");
    await act(async () => {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });
    expect(createReport).toHaveBeenCalledOnce();

    await act(async () => {
      resolveReport({ id: "report-1", status: "pending_review" });
      await Promise.resolve();
    });
    expect(button.disabled).toBe(false);
  });

  it("resets the form and shows success after the report is accepted", async () => {
    const createReport = vi.spyOn(api, "createReport").mockResolvedValue({ id: "report-1", status: "pending_review" });
    await act(async () => root.render(createElement(ListingDetail, { listing })));

    const form = container.querySelector<HTMLFormElement>(".report-form form")!;
    const category = form.querySelector<HTMLSelectElement>('select[name="category"]')!;
    const comment = form.querySelector<HTMLTextAreaElement>('textarea[name="comment"]')!;
    category.value = "incorrect_info";
    comment.value = "Проверьте цену";
    await act(async () => {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await Promise.resolve();
    });

    expect(createReport).toHaveBeenCalledWith("listing-1", { category: "incorrect_info", comment: "Проверьте цену" });
    expect(container.querySelector('[role="status"]')?.textContent).toBe("Жалоба отправлена на проверку.");
    expect(container.querySelector('[role="alert"]')).toBeNull();
    expect(category.value).toBe("");
    expect(comment.value).toBe("");
  });
});
