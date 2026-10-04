import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

const mocks = vi.hoisted(() => ({
  dealers: vi.fn(),
  redirect: vi.fn((url: string): never => { throw new Error(`NEXT_REDIRECT:${url}`); })
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a>
}));
vi.mock("@/lib/server-api", () => ({ serverApi: mocks }));
vi.mock("next/navigation", () => ({ redirect: mocks.redirect }));

import DealersPage from "./page";

const company = {
  id: "company-1",
  slug: "company-one",
  name: "Company One",
  address: "Minsk",
  status: "approved" as const,
  revision: 2,
  listing_count: 3
};

async function renderPage(searchParams: Record<string, string | string[] | undefined> = {}) {
  return renderToStaticMarkup(await DealersPage({ searchParams: Promise.resolve(searchParams) }));
}

describe("dealer directory pagination", () => {
  beforeEach(() => {
    mocks.dealers.mockReset();
    mocks.redirect.mockClear();
  });

  it("requests the selected page and renders accessible previous and next links", async () => {
    mocks.dealers.mockResolvedValueOnce({
      items: [company],
      pagination: { page: 2, page_size: 25, total: 60, pages: 3 }
    });

    const html = await renderPage({ page: "2" });
    const rendered = new DOMParser().parseFromString(html, "text/html");

    expect(mocks.dealers).toHaveBeenCalledWith(2);
    expect(rendered.querySelector('nav[aria-label="Страницы компаний"]')).not.toBeNull();
    expect(rendered.querySelector('a[aria-label="Предыдущая страница, страница 1"]')?.getAttribute("href")).toBe("/dealers");
    expect(rendered.querySelector('a[aria-label="Следующая страница, страница 3"]')?.getAttribute("href")).toBe("/dealers?page=3");
    expect(rendered.querySelector('[aria-current="page"]')?.textContent).toBe("Страница 2 из 3");
  });

  it.each(["-2", "1.5", "oops", ["2", "3"]])("uses page 1 for an invalid page value: %s", async (page) => {
    mocks.dealers.mockResolvedValueOnce({
      items: [company],
      pagination: { page: 1, page_size: 25, total: 3, pages: 1 }
    });

    await renderPage({ page });

    expect(mocks.dealers).toHaveBeenCalledWith(1);
  });

  it("redirects an out-of-range request to the last available page", async () => {
    mocks.dealers.mockResolvedValueOnce({
      items: [],
      pagination: { page: 999, page_size: 25, total: 60, pages: 3 }
    });

    await expect(renderPage({ page: "999" })).rejects.toThrow("NEXT_REDIRECT:/dealers?page=3");
    expect(mocks.redirect).toHaveBeenCalledWith("/dealers?page=3");

    mocks.dealers.mockResolvedValueOnce({
      items: [company],
      pagination: { page: 3, page_size: 25, total: 60, pages: 3 }
    });

    const html = await renderPage({ page: "3" });
    const rendered = new DOMParser().parseFromString(html, "text/html");

    expect(rendered.querySelector('[aria-current="page"]')?.textContent).toBe("Страница 3 из 3");
    expect(rendered.querySelector('a[aria-label="Предыдущая страница, страница 2"]')?.getAttribute("href")).toBe("/dealers?page=2");
    expect(rendered.querySelector('a[aria-label^="Следующая страница"]')).toBeNull();
  });

  it("redirects out-of-range requests to page 1 when there are no pages", async () => {
    mocks.dealers.mockResolvedValueOnce({
      items: [],
      pagination: { page: 9, page_size: 25, total: 0, pages: 0 }
    });

    await expect(renderPage({ page: "9" })).rejects.toThrow("NEXT_REDIRECT:/dealers");
    expect(mocks.redirect).toHaveBeenCalledWith("/dealers");
  });

  it("keeps the empty state without pagination when no companies are approved", async () => {
    mocks.dealers.mockResolvedValueOnce({
      items: [],
      pagination: { page: 1, page_size: 25, total: 0, pages: 0 }
    });

    const html = await renderPage({ page: "1" });

    expect(html).toContain("Компании пока не добавлены");
    expect(html).not.toContain('aria-label="Страницы компаний"');
  });
});
