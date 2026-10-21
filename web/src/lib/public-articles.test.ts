import { beforeEach, describe, expect, it, vi } from "vitest";
import { editorialArticles } from "@/lib/editorial-articles";

const mocks = vi.hoisted(() => ({ articles: vi.fn(), article: vi.fn() }));
vi.mock("@/lib/content-server", () => ({ contentServerApi: { articles: mocks.articles, article: mocks.article } }));

import { loadArticleCards, loadManagedArticle, mergeArticleCards, splitArticleParagraphs } from "@/lib/public-articles";

const summary = (slug: string, title = slug) => ({
  slug, title, summary: `Описание ${slug} для списка статей.`, topic: "inspection" as const,
  published_at: "2026-10-20", updated_at: "2026-10-20T00:00:00Z",
});

beforeEach(() => {
  mocks.articles.mockReset();
  mocks.article.mockReset();
});

describe("mergeArticleCards", () => {
  it("keeps managed order first, then static, and lets a static slug win a collision", () => {
    const staticSlug = editorialArticles[0]!.slug;
    const cards = mergeArticleCards([summary("b"), summary(staticSlug, "Подмена"), summary("a"), summary("b", "Дубль")]);

    expect(cards.map((card) => card.slug)).toEqual(["b", "a", ...editorialArticles.map((item) => item.slug)]);
    expect(cards.find((card) => card.slug === staticSlug)?.origin).toBe("static");
    expect(cards.find((card) => card.slug === "b")?.title).toBe("b");
  });
});

describe("managed article loading", () => {
  it("returns only static cards when the list API fails", async () => {
    mocks.articles.mockRejectedValue(new Error("down"));
    expect((await loadArticleCards()).map((card) => card.slug)).toEqual(editorialArticles.map((item) => item.slug));
  });

  it("pages through the API until the reported total is loaded", async () => {
    mocks.articles
      .mockResolvedValueOnce({ items: [summary("a")], total: 2, page: 1, page_size: 100 })
      .mockResolvedValueOnce({ items: [summary("b")], total: 2, page: 2, page_size: 100 });
    expect((await loadArticleCards()).slice(0, 2).map((card) => card.slug)).toEqual(["a", "b"]);
    expect(mocks.articles).toHaveBeenNthCalledWith(2, undefined, 2, 100);
  });

  it("returns null for a missing article, an API failure, or a mismatched envelope", async () => {
    mocks.article.mockRejectedValueOnce(new Error("404"));
    expect(await loadManagedArticle("x")).toBeNull();
    mocks.article.mockResolvedValueOnce({ content: { kind: "article", key: "other", status: "published" } });
    expect(await loadManagedArticle("x")).toBeNull();
    mocks.article.mockResolvedValueOnce({ content: { kind: "article", key: "x", status: "draft" } });
    expect(await loadManagedArticle("x")).toBeNull();
  });
});

describe("managed article slug validation", () => {
  it("rejects malformed or oversized slugs without calling the API", async () => {
    for (const slug of ["Upper-Case", "a_b", "a--b", "-a", "a-", "a/b", "", "a".repeat(101)]) {
      expect(await loadManagedArticle(slug)).toBeNull();
    }
    expect(mocks.article).not.toHaveBeenCalled();
  });

  it("accepts a valid slug of maximum length", async () => {
    const slug = "a".repeat(100);
    mocks.article.mockResolvedValueOnce({ content: { kind: "article", key: slug, status: "published" } });
    expect(await loadManagedArticle(slug)).not.toBeNull();
  });
});

describe("splitArticleParagraphs", () => {
  it("splits on blank lines and drops empty chunks", () => {
    expect(splitArticleParagraphs("one\nstill one\n\n\n two \n\n")).toEqual(["one\nstill one", "two"]);
  });
});
