import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ catalog: vi.fn() }));
vi.mock("@/lib/server-api", () => ({ serverApi: { catalog: mocks.catalog } }));
vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a>
}));

import MakesPage from "./page";

beforeEach(() => mocks.catalog.mockReset());

describe("make directory", () => {
  it("shows every catalog make, including those beyond the home preview, with working search links", async () => {
    const makes = Array.from({ length: 35 }, (_, index) => ({ id: `id-${index}`, slug: `make-${index}`, name: `Марка ${index}` }));
    mocks.catalog.mockResolvedValue({ items: makes });
    const container = document.createElement("div");
    container.innerHTML = renderToStaticMarkup(await MakesPage());
    const links = Array.from(container.querySelectorAll("ul a"));
    expect(links).toHaveLength(makes.length);
    for (const make of makes) {
      expect(links.some((link) => link.textContent === make.name && link.getAttribute("href") === `/cars/${make.slug}`)).toBe(true);
    }
    expect(mocks.catalog).toHaveBeenCalledWith("makes");
  });

  it("shows an empty state when no makes exist", async () => {
    mocks.catalog.mockResolvedValue({ items: [] });
    expect(renderToStaticMarkup(await MakesPage())).toContain("В справочнике пока нет марок.");
  });

  it("shows a recoverable error when the catalog cannot load", async () => {
    mocks.catalog.mockRejectedValueOnce(new Error("unavailable"));
    const html = renderToStaticMarkup(await MakesPage());
    expect(html).toContain("Справочник марок временно недоступен.");
    expect(html).toContain('href="/makes"');
  });
});
