import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/lib/api";

const mocks = vi.hoisted(() => ({ dealer: vi.fn(), getSavedListingIds: vi.fn(async () => [] as string[]), notFound: vi.fn((): never => { throw new Error("NEXT_NOT_FOUND"); }), redirect: vi.fn((url: string): never => { throw new Error(`NEXT_REDIRECT:${url}`); }) }));

vi.mock("@/lib/server-api", () => ({ serverApi: mocks, getSavedListingIds: mocks.getSavedListingIds }));
vi.mock("@/components/listing-card", () => ({
  ListingCard: ({ listing, saved = false }: { listing: { id: string }; saved?: boolean }) => <div data-listing-id={listing.id} data-favorite-saved={String(saved)} />
}));
vi.mock("next/navigation", () => ({ notFound: mocks.notFound, redirect: mocks.redirect }));

import DealerPage from "./page";

const company = {
  id: "company-1",
  slug: "company-one",
  name: "Company One",
  unp: "123456789",
  address: "Minsk, Main street 1",
  status: "approved" as const,
  revision: 2
};

function dealerResult(phone?: string) {
  return {
    company: { ...company, phone },
    listings: { items: [], pagination: { page: 1, page_size: 25, total: 0, pages: 0 } }
  };
}

const listing = {
  id: "listing-1",
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
  seller: { id: "seller-1", type: "company", name: "Company One" },
  created_at: "2026-09-27T00:00:00Z",
  damaged: false,
  parts_only: false
};

async function renderDealerPage() {
  return renderToStaticMarkup(await DealerPage({ params: Promise.resolve({ slug: company.slug }) }));
}

describe("dealer page public company details", () => {
  it("does not render a public phone link even if an upstream payload contains one", async () => {
    mocks.dealer.mockResolvedValueOnce(dealerResult("+375291234567"));

    const html = await renderDealerPage();

    expect(html).toContain(company.name);
    expect(html).not.toContain("tel:");
    expect(html).toContain(company.address);
  });

  it("marks the user's saved company listings as favorites", async () => {
    mocks.getSavedListingIds.mockResolvedValueOnce([listing.id]);
    mocks.dealer.mockResolvedValueOnce({
      ...dealerResult(),
      listings: { items: [listing], pagination: { page: 1, page_size: 25, total: 1, pages: 1 } }
    });

    const html = await renderDealerPage();

    expect(html).toContain('data-favorite-saved="true"');
  });

  it("shows every weekday and the configured hours on the public company page", async () => {
    mocks.dealer.mockResolvedValueOnce({
      ...dealerResult(),
      company: {
        ...company,
        business_hours: {
          mon: { open: "08:30", close: "17:30" }, tue: { open: "08:30", close: "17:30" },
          wed: { open: "08:30", close: "17:30" }, thu: { open: "08:30", close: "17:30" },
          fri: { open: "08:30", close: "17:30" }, sat: { closed: true }, sun: { closed: true }
        }
      }
    });

    const html = await renderDealerPage();

    expect(html).toContain("Режим работы");
    expect(html).toContain("Понедельник");
    expect(html).toContain("08:30–17:30");
    expect(html).toContain("Суббота");
    expect(html).toContain("Воскресенье");
    expect(html).toContain("Закрыто");
  });

  it("explains when a company has not published business hours", async () => {
    mocks.dealer.mockResolvedValueOnce(dealerResult());

    const html = await renderDealerPage();

    expect(html).toContain("Режим работы не указан");
  });

  it("shows a temporary error instead of a 404 when the API is unavailable", async () => {
    mocks.dealer.mockRejectedValueOnce(new ApiClientError(503, { message: "Временно недоступно" }));

    const html = await renderDealerPage();

    expect(html).toContain("Страница компании временно недоступна");
    expect(html).toContain('href="/dealers"');
    expect(mocks.notFound).not.toHaveBeenCalled();
  });

  it("keeps a genuine missing company as a 404", async () => {
    mocks.dealer.mockRejectedValueOnce(new ApiClientError(404, { message: "Не найдено" }));

    await expect(renderDealerPage()).rejects.toThrow("NEXT_NOT_FOUND");
  });

  it("requests the selected listing page and exposes keyboard-friendly pagination", async () => {
    mocks.dealer.mockResolvedValueOnce({
      ...dealerResult(),
      listings: { items: [], pagination: { page: 2, page_size: 25, total: 51, pages: 3 } }
    });

    const html = renderToStaticMarkup(await DealerPage({ params: Promise.resolve({ slug: company.slug }), searchParams: Promise.resolve({ page: "2" }) }));
    const rendered = new DOMParser().parseFromString(html, "text/html");

    expect(mocks.dealer).toHaveBeenCalledWith(company.slug, 2);
    expect(rendered.querySelector('nav[aria-label="Страницы объявлений компании"]')).not.toBeNull();
    expect(rendered.querySelector('a[aria-label="Предыдущая страница, страница 1"]')?.getAttribute("href")).toBe(`/dealers/${company.slug}`);
    expect(rendered.querySelector('[aria-current="page"]')?.textContent).toBe("Страница 2 из 3");
  });
});
