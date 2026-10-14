import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ListingDetail } from "@/components/listing-detail";
import { api, ApiClientError } from "@/lib/api";
import type { Listing } from "@/lib/types";

const routerMocks = vi.hoisted(() => ({ push: vi.fn() }));
const authMocks = vi.hoisted(() => ({ user: null as { id: string } | null }));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a>
}));
vi.mock("next/image", () => ({
  default: ({ unoptimized: _unoptimized, priority: _priority, ...props }: React.ImgHTMLAttributes<HTMLImageElement> & { unoptimized?: boolean; priority?: boolean }) => <img {...props} />
}));
vi.mock("next/navigation", () => ({ useRouter: () => routerMocks }));
vi.mock("@/components/auth-provider", () => ({ useAuth: () => ({ user: authMocks.user }) }));
vi.mock("@/components/compare-button", () => ({ CompareButton: ({ listingId }: { listingId: string }) => <button data-compare-listing={listingId}>Сравнить</button> }));
vi.mock("@/components/share-button", () => ({ ShareButton: ({ title }: { href: string; title: string }) => <button>Поделиться {title}</button> }));

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  authMocks.user = null;
  vi.spyOn(api, "guestContactEnabled").mockResolvedValue({ guest_contact_reveal_enabled: false });
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
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
  it("takes a guest to login with the new chat route as the next path", async () => {
    await act(async () => root.render(createElement(ListingDetail, { listing })));

    const link = container.querySelector<HTMLAnchorElement>(".contact-chat");
    expect(link?.textContent).toContain("Написать продавцу");
    expect(link?.getAttribute("href")).toBe(`/login?next=${encodeURIComponent(`/account/messages/new?listing_id=${listing.id}`)}`);
  });

  it("lets a guest explicitly reveal a phone only when the public capability is enabled", async () => {
    vi.spyOn(api, "guestContactEnabled").mockResolvedValue({ guest_contact_reveal_enabled: true });
    const revealPhone = vi.spyOn(api, "revealPhone").mockResolvedValue({
      phone: "+375 29 000 00 00",
      messengers: [
        { channel: "telegram", uri: "https://t.me/seller", opted_in: true },
        { channel: "viber", uri: "https://viber.me/seller", opted_in: true }
      ]
    });
    await act(async () => {
      root.render(createElement(ListingDetail, { listing }));
      await Promise.resolve();
    });

    expect(container.textContent).toContain("Телефон можно посмотреть без входа в аккаунт.");
    expect(container.textContent).not.toContain("+375 29 000 00 00");
    expect(container.querySelector('a[href="https://t.me/seller"]')).toBeNull();
    expect(container.querySelector('a[href="https://viber.me/seller"]')).toBeNull();
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
    expect(container.querySelector('a[href="https://t.me/seller"]')?.textContent).toContain("Telegram");
    expect(container.querySelector('a[href="https://viber.me/seller"]')?.textContent).toContain("Viber");
    expect(container.querySelector('[data-compare-listing="listing-1"]')).not.toBeNull();
    expect(container.textContent).toContain("Поделиться Марка Модель");
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

describe("owner promotion entry", () => {
  it("shows the listing promotion entry only to its owner", async () => {
    await act(async () => root.render(createElement(ListingDetail, { listing })));
    expect(container.querySelector('a[href="/account/billing?listing_id=listing-1"]')).toBeNull();

    authMocks.user = { id: "another-user" };
    await act(async () => root.render(createElement(ListingDetail, { listing })));
    expect(container.querySelector('a[href="/account/billing?listing_id=listing-1"]')).toBeNull();

    authMocks.user = { id: listing.seller.id };
    await act(async () => root.render(createElement(ListingDetail, { listing })));
    expect(container.querySelector<HTMLAnchorElement>('a[href="/account/billing?listing_id=listing-1"]')?.textContent).toContain("Услуги продвижения");
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
    expect(facts).toContain("ABS");
    expect(facts).toContain("Центральный");
    expect(facts).toContain("9:00–20:00");
    expect(container.querySelector(".listing-trust")?.textContent).toContain("Указано продавцом");
    expect(container.querySelector(".listing-trust")?.textContent).toContain("Торг: Возможен");
    expect(container.textContent).toContain("Похожие объявления");
    const relatedLink = container.querySelector<HTMLAnchorElement>('.related-listings .card-title[href="/cars/marka/model/related-1"]');
    expect(relatedLink?.textContent).toBe("Похожий автомобиль");
  });

  it("does not show the current listing twice and caps related results at eight", async () => {
    const items = Array.from({ length: 10 }, (_, index) => ({ ...listing, id: `related-${index}`, title: `Автомобиль ${index}` }));
    await act(async () => root.render(createElement(ListingDetail, { listing, relatedListings: [{ ...listing }, ...items] })));
    expect(container.querySelectorAll(".related-listings .listing-card")).toHaveLength(8);
    expect(container.querySelector('.related-listings a[href$="listing-1"]')).toBeNull();
  });

  it("shows other active listings from the same seller", async () => {
    const sellerListing = { ...listing, id: "seller-other", status: "active" as const, title: "Ещё одно объявление" };
    await act(async () => root.render(createElement(ListingDetail, { listing, sellerListings: [sellerListing] })));
    expect(container.querySelector("#seller-listings-heading")?.textContent).toBe("Другие объявления продавца");
    expect(container.textContent).toContain("Ещё одно объявление");
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
