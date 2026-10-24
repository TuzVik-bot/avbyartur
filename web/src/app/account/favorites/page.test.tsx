import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  favorites: vi.fn(),
  requireSession: vi.fn()
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a>
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/server-api", () => ({ serverApi: mocks }));
vi.mock("@/lib/server", () => ({ requireSession: mocks.requireSession }));
vi.mock("@/components/listing-card", () => ({ ListingCard: ({ listing }: { listing: { title: string } }) => <article>{listing.title}</article> }));

import FavoritesPage from "./page";

const favorite = {
  id: "listing-1",
  slug: "listing-1",
  title: "Марка Модель",
  make: null,
  model: null,
  year: 2020,
  mileage_km: 50000,
  fuel: "petrol",
  transmission: "manual",
  drive: "front",
  price: { amount: "10000", currency: "BYN" as const },
  region: null,
  city: null,
  seller: { type: "private" as const, id: "seller-1", name: "Продавец" },
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-01T00:00:00Z",
  damaged: false,
  parts_only: false,
  price_drop_notifications_enabled: false
};

describe("FavoritesPage price alerts", () => {
  it("explains the limited price-drop opt-in and links to the inbox settings", async () => {
    mocks.requireSession.mockResolvedValue({ user: { id: "user-1" } });
    mocks.favorites.mockResolvedValue({ items: [favorite] });

    const html = renderToStaticMarkup(await FavoritesPage());

    expect(mocks.requireSession).toHaveBeenCalledWith("/account/favorites");
    expect(html).toContain("после включения продавец снизит цену в той же валюте");
    expect(html).toContain("Снижения до включения не рассылаются.");
    expect(html).toContain('href="/account/notifications"');
    expect(html).toContain("Входящие и настройки уведомлений");
    expect(html).toContain("Марка Модель");
  });

  it("keeps failed favorite loading distinct from an empty favorite list", async () => {
    mocks.requireSession.mockResolvedValue({ user: { id: "user-1" } });
    mocks.favorites.mockRejectedValue(new Error("offline"));

    const html = renderToStaticMarkup(await FavoritesPage());

    expect(html).toContain("Не удалось загрузить избранное");
    expect(html).not.toContain("Здесь пока пусто");
  });
});
