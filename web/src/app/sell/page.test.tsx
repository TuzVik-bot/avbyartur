import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  catalog: vi.fn(),
  regions: vi.fn(),
  company: vi.fn(),
  listing: vi.fn(),
  photos: vi.fn(),
  getSessionServer: vi.fn()
}));

vi.mock("next/link", () => ({ default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a> }));
vi.mock("next/image", () => ({ default: (props: Record<string, unknown>) => createElement("img", props) }));
vi.mock("@/components/sell-form", () => ({ SellForm: (props: { makes: unknown[]; regions: unknown[]; initialListing?: { id: string } | null; initialCategoryCode?: string; initialSubcategory?: string }) => createElement("div", { "data-makes": props.makes.length, "data-regions": props.regions.length, "data-listing-id": props.initialListing?.id || "", "data-category-code": props.initialCategoryCode || "", "data-subcategory": props.initialSubcategory || "" }) }));
vi.mock("@/lib/server-api", () => ({ serverApi: mocks, getSessionServer: mocks.getSessionServer }));

import SellPage, { metadata } from "./page";

describe("seller landing and listing form", () => {
  it("shows a seller landing to guests and sends them back to the requested form after login", async () => {
    mocks.getSessionServer.mockResolvedValue(null);

    const html = renderToStaticMarkup(await SellPage({ searchParams: Promise.resolve({}) }));

    expect(html).toContain("От черновика до объявления в каталоге");
    expect(html).toContain("Три этапа до публикации");
    expect(html).toContain("Телефон скрыт в выдаче");
    expect(html).toContain("Подойдут JPEG, PNG и WebP");
    expect(html).not.toContain("5 минут");
    expect(html).not.toContain("HEIC");
    expect(html).toContain('href="/login?next=%2Fsell"');
    expect(html).not.toContain("data-makes");
    expect(metadata.robots).toEqual({ index: false, follow: false });
  });

  it("keeps the edit listing in the login return path", async () => {
    mocks.getSessionServer.mockResolvedValue(null);

    const html = renderToStaticMarkup(await SellPage({ searchParams: Promise.resolve({ listing: "listing-26" }) }));

    expect(html).toContain('href="/login?next=%2Fsell%3Flisting%3Dlisting-26"');
  });

  it("preserves category and valid subcategory through guest login", async () => {
    mocks.getSessionServer.mockResolvedValue(null);

    const html = renderToStaticMarkup(await SellPage({ searchParams: Promise.resolve({ category_code: "motorcycles", subcategory: "motorcycle" }) }));

    expect(html).toContain("Новое объявление мототехники");
    expect(html).toContain("Вы выбрали: Мотоцикл");
    expect(html).toContain('href="/login?next=%2Fsell%3Fcategory_code%3Dmotorcycles%26subcategory%3Dmotorcycle"');
  });

  it("drops an invalid subcategory before rendering or building a login return URL", async () => {
    mocks.getSessionServer.mockResolvedValue(null);

    const html = renderToStaticMarkup(await SellPage({ searchParams: Promise.resolve({ category_code: "watercraft", subcategory: "not-a-subcategory" }) }));

    expect(html).not.toContain("Вы выбрали:");
    expect(html).toContain('href="/login?next=%2Fsell%3Fcategory_code%3Dwatercraft"');
  });

  it("propagates session API failures instead of presenting them as a guest state", async () => {
    mocks.getSessionServer.mockRejectedValue(new Error("session service unavailable"));

    await expect(SellPage({ searchParams: Promise.resolve({}) })).rejects.toThrow("session service unavailable");
  });

  it("explains unavailable required reference data and leaves manual make entry available", async () => {
    mocks.getSessionServer.mockResolvedValue({ user: { display_name: "Тест" } });
    mocks.catalog.mockImplementation(async (kind: string) => {
      if (kind === "makes") throw new Error("catalog offline");
      return { items: [] };
    });
    mocks.regions.mockRejectedValueOnce(new Error("locations offline"));
    mocks.company.mockResolvedValue({ company: null });

    const html = renderToStaticMarkup(await SellPage({ searchParams: Promise.resolve({}) }));

    expect(html).toContain("Марку можно указать вручную");
    expect(html).toContain("отправить его на проверку получится после загрузки справочника");
    expect(html).toContain("data-makes=\"0\"");
    expect(html).toContain("data-regions=\"0\"");
    expect(html).toContain('href="/sell"');
  });

  it("passes category and subcategory into the authenticated form", async () => {
    mocks.getSessionServer.mockResolvedValue({ user: { display_name: "Тест" } });
    mocks.catalog.mockResolvedValue({ items: [] });
    mocks.regions.mockResolvedValue({ items: [] });
    mocks.company.mockResolvedValue({ company: null });

    const html = renderToStaticMarkup(await SellPage({ searchParams: Promise.resolve({ category_code: "tires", subcategory: "passenger" }) }));

    expect(html).toContain('data-category-code="tires"');
    expect(html).toContain('data-subcategory="passenger"');
  });

  it("loads an edit listing by ID even when it is beyond the first owner page", async () => {
    mocks.getSessionServer.mockResolvedValue({ user: { display_name: "Тест" } });
    mocks.catalog.mockResolvedValue({ items: [] });
    mocks.regions.mockResolvedValue({ items: [] });
    mocks.company.mockResolvedValue({ company: null });
    mocks.listing.mockResolvedValueOnce({ listing: {
      id: "listing-26",
      slug: "listing-26",
      title: "Audi A3",
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
      seller: { type: "company", id: "seller-1", name: "Тест" },
      created_at: "2026-09-28T00:00:00Z",
      damaged: false,
      parts_only: false,
      description: "",
      condition: null,
      photo_urls: []
    } });
    mocks.photos.mockResolvedValueOnce({ items: [] });

    const html = renderToStaticMarkup(await SellPage({ searchParams: Promise.resolve({ listing: "listing-26" }) }));

    expect(mocks.listing).toHaveBeenCalledWith("listing-26");
    expect(html).toContain('data-listing-id="listing-26"');
  });
});
