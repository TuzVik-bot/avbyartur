import { renderToStaticMarkup } from "react-dom/server";
import type { Metadata } from "next";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/search-route", () => ({
  SearchRoute: ({ search }: { search: { category_code: string } }) => <div data-category={search.category_code} />,
}));

const pages = import.meta.glob("./*/page.tsx") as Record<string, () => Promise<{ default: () => ReactElement; metadata: Metadata }>>;

describe("footer category routes", () => {
  it.each([
    ["buses", "Автобусы"],
    ["trucks", "Грузовики"],
    ["parts", "Запчасти и автотовары"],
    ["trailers", "Прицепы"],
  ])("serves /%s with its own heading, search and canonical", async (slug, title) => {
    const load = pages[`./${slug}/page.tsx`];
    expect(load).toBeTypeOf("function");
    const { default: Page, metadata } = await load();
    const container = document.createElement("div");
    container.innerHTML = renderToStaticMarkup(<Page />);
    expect(container.querySelector("h1")?.textContent).toBe(title);
    expect(container.querySelector("[data-category]")?.getAttribute("data-category")).toBe(slug);
    expect(new URL(String(metadata.alternates?.canonical)).pathname).toBe(`/${slug}`);
  });
});
