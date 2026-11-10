import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  meListings: vi.fn(),
  listingPromotionEligibility: vi.fn(),
  requireSession: vi.fn()
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a>
}));
vi.mock("@/lib/server-api", () => ({ serverApi: mocks }));
vi.mock("@/lib/server", () => ({ requireSession: mocks.requireSession }));
vi.mock("@/components/listing-status-actions", () => ({
  ListingStatusActions: () => <div data-testid="listing-actions" />
}));

import AccountListingsPage from "./page";

describe("account listing drafts", () => {
  it("shows promotion CTA only when the protected listing-specific check permits it", async () => {
    mocks.requireSession.mockResolvedValue({ user: { display_name: "Тест", email: "pilot@example.com" } });
    mocks.meListings.mockResolvedValueOnce({ items: [{
      id: "company-listing", slug: "company-listing", title: "Audi A3", status: "active", revision: 1,
      make: null, model: null, generation: null, year: null, mileage_km: null, fuel: null, transmission: null,
      drive: null, price: null, region: null, city: null,
      seller: { type: "company", id: "company-1", name: "Тест" }, created_at: "2026-09-28T00:00:00Z",
      damaged: false, parts_only: false
    }] });
    mocks.listingPromotionEligibility.mockResolvedValueOnce({ promotable: false });

    const deniedHtml = renderToStaticMarkup(await AccountListingsPage({ searchParams: Promise.resolve({}) }));
    expect(mocks.listingPromotionEligibility).toHaveBeenCalledWith("company-listing");
    expect(deniedHtml).not.toContain("Услуги продвижения");

    mocks.meListings.mockResolvedValueOnce({ items: [{
      id: "company-listing", slug: "company-listing", title: "Audi A3", status: "active", revision: 1,
      make: null, model: null, generation: null, year: null, mileage_km: null, fuel: null, transmission: null,
      drive: null, price: null, region: null, city: null,
      seller: { type: "company", id: "company-1", name: "Тест" }, created_at: "2026-09-28T00:00:00Z",
      damaged: false, parts_only: false
    }] });
    mocks.listingPromotionEligibility.mockResolvedValueOnce({ promotable: true });
    const allowedHtml = renderToStaticMarkup(await AccountListingsPage({ searchParams: Promise.resolve({}) }));
    expect(allowedHtml).toContain("Услуги продвижения");
  });

  it("offers a repeatable retry when the listing request fails and preserves the requested page", async () => {
    mocks.requireSession.mockResolvedValue({ user: { display_name: "Тест", email: "pilot@example.com" } });
    mocks.meListings.mockRejectedValueOnce(new Error("offline"));

    const firstAttempt = renderToStaticMarkup(await AccountListingsPage({
      searchParams: Promise.resolve({ page: "2" })
    }));

    expect(firstAttempt).toContain("Не удалось загрузить объявления.");
    expect(firstAttempt).toContain('role="alert"');
    expect(firstAttempt).toContain("Повторить загрузку");
    expect(firstAttempt).toContain('href="/account/listings?page=2&amp;retry=1"');

    mocks.meListings.mockRejectedValueOnce(new Error("still offline"));
    const secondAttempt = renderToStaticMarkup(await AccountListingsPage({
      searchParams: Promise.resolve({ page: "2", retry: "1" })
    }));

    expect(secondAttempt).toContain('href="/account/listings?page=2&amp;retry=2"');
  });

  it("keeps a partial draft visible when make and model have not been selected", async () => {
    mocks.requireSession.mockResolvedValue({ user: { display_name: "Тест", email: "pilot@example.com" } });
    mocks.meListings.mockResolvedValueOnce({
      items: [{
        id: "draft-1",
        slug: "draft-1",
        title: "",
        status: "draft",
        revision: 1,
        make: null,
        model: null,
        generation: null,
        year: null,
        mileage_km: null,
        fuel: null,
        transmission: null,
        drive: null,
        price: null,
        region: null,
        city: null,
        seller: { type: "private", id: "seller-1", name: "Тест" },
        created_at: "2026-09-28T00:00:00Z",
        damaged: false,
        parts_only: false
      }]
    });

    const html = renderToStaticMarkup(await AccountListingsPage({ searchParams: Promise.resolve({}) }));

    expect(html).toContain("Черновик без выбранного автомобиля");
    expect(html).toContain('href="/sell?listing=draft-1"');
    expect(html).toContain("Черновик");
  });

  it("shows the moderator reason for a rejected listing", async () => {
    mocks.requireSession.mockResolvedValue({ user: { display_name: "Тест", email: "pilot@example.com" } });
    mocks.meListings.mockResolvedValueOnce({ items: [{
      id: "rejected-1",
      slug: "rejected-1",
      title: "Audi A3",
      status: "rejected",
      revision: 3,
      moderation_reason: "Добавьте читаемое фото VIN.",
      make: null,
      model: null,
      generation: null,
      year: null,
      mileage_km: null,
      fuel: null,
      transmission: null,
      drive: null,
      price: null,
      region: null,
      city: null,
      seller: { type: "private", id: "seller-1", name: "Тест" },
      created_at: "2026-09-28T00:00:00Z",
      damaged: false,
      parts_only: false
    }] });

    const html = renderToStaticMarkup(await AccountListingsPage({ searchParams: Promise.resolve({}) }));

    expect(html).toContain("Добавьте читаемое фото VIN.");
  });

  it("requests the selected page and renders previous and next links", async () => {
    mocks.requireSession.mockResolvedValue({ user: { display_name: "Тест", email: "pilot@example.com" } });
    mocks.meListings.mockResolvedValueOnce({
      items: [{
        id: "listing-26",
        slug: "listing-26",
        title: "Audi A3",
        status: "active",
        revision: 1,
        make: null,
        model: null,
        generation: null,
        year: null,
        mileage_km: null,
        fuel: null,
        transmission: null,
        drive: null,
        price: null,
        region: null,
        city: null,
        seller: { type: "company", id: "seller-1", name: "Тест" },
        created_at: "2026-09-28T00:00:00Z",
        damaged: false,
        parts_only: false
      }],
      pagination: { page: 2, page_size: 25, total: 75, pages: 3 }
    });

    const html = renderToStaticMarkup(await AccountListingsPage({ searchParams: Promise.resolve({ page: "2" }) }));

    expect(mocks.meListings).toHaveBeenLastCalledWith(2);
    expect(html).toContain('href="/account/listings"');
    expect(html).toContain('href="/account/listings?page=3"');
    expect(html).toContain("Страница 2 из 3");
    expect(html).toContain('href="/sell?listing=listing-26"');
  });

  it("shows a market price hint with a price edit link only for active listings with comparison data", async () => {
    mocks.requireSession.mockResolvedValue({ user: { display_name: "Тест", email: "pilot@example.com" } });
    const base = {
      slug: "x", revision: 2, make: null, model: null, generation: null, year: 2018, mileage_km: 90000, fuel: "petrol",
      transmission: "manual", drive: null, region: null, city: null,
      seller: { type: "private", id: "seller-1", name: "Тест" }, created_at: "2026-09-28T00:00:00Z",
      damaged: false, parts_only: false
    };
    const comparison = { median_byn: "10000.00", sample_size: 12, seller_count: 6, as_of: "2026-11-10T00:00:00Z", rate_date: null };
    mocks.meListings.mockResolvedValueOnce({ items: [
      { ...base, id: "above", title: "Above", status: "active", price: { amount: "12000.00", currency: "BYN", market_comparison: { ...comparison, label: "above_market", difference_percent: 20 } } },
      { ...base, id: "below", title: "Below", status: "active", price: { amount: "8500.00", currency: "BYN", market_comparison: { ...comparison, label: "below_market", difference_percent: -15 } } },
      { ...base, id: "unknown", title: "Unknown", status: "active", price: { amount: "9000.00", currency: "BYN", market_comparison: null } },
      { ...base, id: "paused", title: "Paused", status: "paused", price: { amount: "12000.00", currency: "BYN", market_comparison: { ...comparison, label: "above_market", difference_percent: 20 } } }
    ] });
    mocks.listingPromotionEligibility.mockResolvedValue({ promotable: false });

    const html = renderToStaticMarkup(await AccountListingsPage({ searchParams: Promise.resolve({}) }));

    expect(html).toContain("Цена выше рынка на 20%");
    expect(html).toContain("Цена ниже рынка на 15%");
    expect(html.match(/data-market-hint/g)).toHaveLength(2);
    expect(html.match(/>Изменить цену</g)).toHaveLength(2);
    expect(html).toMatch(/data-market-hint[^]*?href="\/sell\?listing=above"[^>]*>Изменить цену</);
  });
});
