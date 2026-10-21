import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ArticlesPage from "@/app/useful-information/articles/page";
import ArticleDetailPage, { generateMetadata, generateStaticParams } from "@/app/useful-information/articles/[slug]/page";
import { editorialArticles } from "@/lib/editorial-articles";

const mocks = vi.hoisted(() => ({ articles: vi.fn(), article: vi.fn() }));
vi.mock("@/lib/content-server", () => ({ contentServerApi: { articles: mocks.articles, article: mocks.article } }));

const managedSummary = {
  slug: "novaya-statya", title: "Новая управляемая статья", summary: "Краткое описание управляемой статьи для списка.",
  topic: "vin", published_at: "2026-10-20", updated_at: "2026-10-21T09:00:00Z",
};
const managedDetail = {
  content: {
    id: "1", kind: "article", key: "novaya-statya", status: "published", revision: 2, updated_at: "2026-10-21T09:00:00Z",
    payload: {
      slug: "novaya-statya", title: "Новая управляемая статья", summary: managedSummary.summary, topic: "vin",
      body: "Первый абзац <b>без разметки</b>.\n\nВторой абзац.", published_at: "2026-10-20",
      sources: [{ title: "Официальный источник", url: "https://example.gov.by/x" }, { title: "Плохой", url: "javascript:alert(1)" }],
    },
  },
  indexable: false,
};

beforeEach(() => {
  mocks.articles.mockReset().mockRejectedValue(new Error("api down"));
  mocks.article.mockReset().mockRejectedValue(new Error("api down"));
});

describe("public editorial pages", () => {
  it("lists the three prepared articles with stable internal links", async () => {
    const html = renderToStaticMarkup(await ArticlesPage());

    for (const article of editorialArticles) {
      expect(html).toContain(article.title);
      expect(html).toContain(`/useful-information/articles/${article.slug}`);
      expect(html).toContain(article.section);
    }
  });

  it("prebuilds only the editorial article slugs", () => {
    expect(generateStaticParams()).toEqual(editorialArticles.map(({ slug }) => ({ slug })));
  });

  it("renders the complete article content and links to related instructions", async () => {
    const article = editorialArticles[0];
    if (!article) throw new Error("Expected at least one editorial article");

    const html = renderToStaticMarkup(await ArticleDetailPage({ params: Promise.resolve({ slug: article.slug }) }));

    expect(html).toContain(article.title);
    expect(html).toContain(article.closingText);
    expect(html).toContain("Организуйте независимую диагностику");
    expect(html).toContain("/useful-information/articles/kak-vybrat-avtoservis");
  });

  it("sets an article-specific title, summary, and canonical route", async () => {
    const article = editorialArticles[0];
    if (!article) throw new Error("Expected at least one editorial article");

    const metadata = await generateMetadata({ params: Promise.resolve({ slug: article.slug }) });
    const canonical = metadata.alternates?.canonical;

    expect(metadata.title).toBe(article.title);
    expect(metadata.description).toBe(article.description);
    expect(new URL(String(canonical)).pathname).toBe(`/useful-information/articles/${article.slug}`);
  });

  it("puts published managed articles before the static ones", async () => {
    mocks.articles.mockResolvedValue({ items: [managedSummary], total: 1, page: 1, page_size: 100 });
    const html = renderToStaticMarkup(await ArticlesPage());

    expect(html).toContain("/useful-information/articles/novaya-statya");
    expect(html.indexOf("Новая управляемая статья")).toBeLessThan(html.indexOf(editorialArticles[0]!.title));
  });

  it("still lists static articles when the API is unavailable", async () => {
    const html = renderToStaticMarkup(await ArticlesPage());
    for (const article of editorialArticles) expect(html).toContain(article.title);
  });

  it("falls back to a managed article for a non-static slug and escapes its text", async () => {
    mocks.article.mockResolvedValue(managedDetail);
    const html = renderToStaticMarkup(await ArticleDetailPage({ params: Promise.resolve({ slug: "novaya-statya" }) }));

    expect(html).toContain("Новая управляемая статья");
    expect(html).toContain("&lt;b&gt;без разметки&lt;/b&gt;");
    expect(html).not.toContain("<b>");
    expect(html).toContain("Второй абзац.");
    expect(html).toContain("Обновлено 21 октября 2026");
    expect(html).toContain("https://example.gov.by/x");
    expect(html).not.toContain("javascript:");
    expect(html).not.toContain("Что сделать дальше");
  });

  it("does not call the API for static slugs", async () => {
    await ArticleDetailPage({ params: Promise.resolve({ slug: editorialArticles[0]!.slug }) });
    expect(mocks.article).not.toHaveBeenCalled();
  });

  it("returns not found for unknown slugs and for API failures", async () => {
    await expect(ArticleDetailPage({ params: Promise.resolve({ slug: "missing" }) })).rejects.toThrow();
    const metadata = await generateMetadata({ params: Promise.resolve({ slug: "missing" }) });
    expect(metadata.robots).toEqual({ index: false, follow: false });
  });

  it("builds metadata for a managed article", async () => {
    mocks.article.mockResolvedValue(managedDetail);
    const metadata = await generateMetadata({ params: Promise.resolve({ slug: "novaya-statya" }) });
    expect(metadata.title).toBe("Новая управляемая статья");
    expect(new URL(String(metadata.alternates?.canonical)).pathname).toBe("/useful-information/articles/novaya-statya");
  });
});
