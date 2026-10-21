import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import ArticlesPage from "@/app/useful-information/articles/page";
import ArticleDetailPage, { generateMetadata, generateStaticParams } from "@/app/useful-information/articles/[slug]/page";
import { editorialArticles } from "@/lib/editorial-articles";

describe("public editorial pages", () => {
  it("lists the three prepared articles with stable internal links", () => {
    const html = renderToStaticMarkup(<ArticlesPage />);

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
});
