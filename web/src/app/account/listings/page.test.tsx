import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  meListings: vi.fn(),
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
});
