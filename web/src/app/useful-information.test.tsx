import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";
import { ApiClientError } from "@/lib/api";
import { contentServerApi } from "@/lib/content-server";
import UsefulInformationArticlePage, { metadata as articleMetadata } from "@/app/useful-information/[slug]/page";
import UsefulInformationPage, { metadata as listMetadata } from "@/app/useful-information/page";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a>
}));
vi.mock("next/navigation", () => ({
  notFound: () => { throw new Error("NEXT_NOT_FOUND"); },
  redirect: (url: string) => { throw new Error(`NEXT_REDIRECT:${url}`); }
}));
vi.mock("@/lib/content-server", () => ({ contentServerApi: { articles: vi.fn(), article: vi.fn() } }));

const summary = {
  slug: "vin-check-basics", title: "Что показывает VIN-проверка",
  summary: "Как читать результат и какие ограничения учитывать при проверке истории автомобиля.",
  topic: "vin" as const, published_at: "2026-10-04", updated_at: "2026-10-04T10:00:00Z"
};

it("keeps both article routes explicitly out of search indexes", () => {
  for (const metadata of [listMetadata, articleMetadata]) {
    expect(metadata.robots).toEqual({ index: false, follow: false, noarchive: true, googleBot: { index: false, follow: false, noimageindex: true } });
  }
});

it("passes valid topic filters to the public article list and shows an empty published state", async () => {
  vi.mocked(contentServerApi.articles).mockResolvedValueOnce({ items: [summary], total: 1, page: 1, page_size: 20 })
    .mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 20 });
  const filtered = renderToStaticMarkup(await UsefulInformationPage({ searchParams: Promise.resolve({ topic: "vin" }) }));
  expect(contentServerApi.articles).toHaveBeenNthCalledWith(1, "vin", 1);
  expect(filtered).toContain("Что показывает VIN-проверка");

  const invalidFilter = renderToStaticMarkup(await UsefulInformationPage({ searchParams: Promise.resolve({ topic: "untrusted" }) }));
  expect(contentServerApi.articles).toHaveBeenNthCalledWith(2, undefined, 1);
  expect(invalidFilter).toContain("Пока нет опубликованных материалов");
});

it("loads a selected article page and preserves the topic in navigation", async () => {
  vi.mocked(contentServerApi.articles).mockResolvedValueOnce({ items: [summary], total: 45, page: 2, page_size: 20 });
  const html = renderToStaticMarkup(await UsefulInformationPage({ searchParams: Promise.resolve({ topic: "vin", page: "2" }) }));
  expect(contentServerApi.articles).toHaveBeenLastCalledWith("vin", 2);
  expect(html).toContain('aria-label="Страницы материалов"');
  expect(html).toContain('href="/useful-information?topic=vin"');
  expect(html).toContain('href="/useful-information?topic=vin&amp;page=3"');
  expect(html).toContain("Страница 2 из 3");
});

it.each(["0", "-1", "1.5", "oops", "99999999999999999999", ["2", "3"]])("uses page 1 for invalid page %s", async (page) => {
  vi.mocked(contentServerApi.articles).mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 20 });
  await UsefulInformationPage({ searchParams: Promise.resolve({ page }) });
  expect(contentServerApi.articles).toHaveBeenLastCalledWith(undefined, 1);
});

it("redirects an out-of-range page to the last available filtered page", async () => {
  vi.mocked(contentServerApi.articles).mockResolvedValueOnce({ items: [], total: 21, page: 9, page_size: 20 });
  await expect(UsefulInformationPage({ searchParams: Promise.resolve({ topic: "vin", page: "9" }) }))
    .rejects.toThrow("NEXT_REDIRECT:/useful-information?topic=vin&page=2");
});

it("renders a published article and hides draft or missing slugs as not found", async () => {
  vi.mocked(contentServerApi.article).mockResolvedValueOnce({
    indexable: false,
    content: {
      id: "article-1", kind: "article", key: "vin-check-basics", status: "published", revision: 1,
      updated_at: "2026-10-04T10:00:00Z",
      payload: { ...summary, body: "Сверьте идентификаторы.\n\nПрочитайте ограничения отчёта.", sources: [] }
    }
  });
  const article = renderToStaticMarkup(await UsefulInformationArticlePage({ params: Promise.resolve({ slug: summary.slug }) }));
  expect(contentServerApi.article).toHaveBeenCalledWith(summary.slug);
  expect(article).toContain("Что показывает VIN-проверка");
  expect(article).toContain('href="/vin-check"');

  vi.mocked(contentServerApi.article).mockRejectedValueOnce(new ApiClientError(404, { message: "Not found" }));
  await expect(UsefulInformationArticlePage({ params: Promise.resolve({ slug: "draft-article" }) })).rejects.toThrow("NEXT_NOT_FOUND");
});
