import { existsSync } from "node:fs";
import { join } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import ArticlesPage from "@/app/useful-information/articles/page";
import ArticleDetailPage, { generateMetadata, generateStaticParams } from "@/app/useful-information/articles/[slug]/page";
import { editorialArticles } from "@/lib/editorial-articles";
import { editorialContentUpdated, editorialGuideActions } from "@/lib/editorial-guide-actions";

const publicDir = join(process.cwd(), "public");

describe("public editorial pages", () => {
  it("lists every published article with stable internal links", () => {
    const html = renderToStaticMarkup(<ArticlesPage />);

    for (const article of editorialArticles) {
      expect(html).toContain(article.title);
      expect(html).toContain(`/useful-information/articles/${article.slug}`);
      expect(html).toContain(article.section);
      expect(html).toContain("мин чтения");
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
    expect(html).toContain("мин чтения");
    expect(html).toContain("Организуйте независимую диагностику");
    expect(html).toContain("/useful-information/articles/kak-vybrat-avtoservis");
  });

  it("keeps every referenced editorial photo on disk", () => {
    for (const article of editorialArticles) {
      const sources = [
        ...(article.leadImage ? [article.leadImage.src] : []),
        ...article.sections.flatMap((section) => section.blocks
          .filter((block): block is Extract<typeof block, { type: "image" }> => block.type === "image")
          .map((block) => block.src)),
      ];
      for (const src of sources) {
        expect(src.startsWith("/editorial/"), src).toBe(true);
        expect(existsSync(join(publicDir, src)), `missing file: ${src}`).toBe(true);
      }
    }
  });

  it("shows editorial ownership and relevant next steps for every guide", async () => {
    for (const article of editorialArticles) {
      const html = renderToStaticMarkup(await ArticleDetailPage({ params: Promise.resolve({ slug: article.slug }) }));

      expect(html).toContain(article.source ? "Материал по лицензии" : "Редакционный материал");
      expect(html).toContain(`Обновлено ${editorialContentUpdated}`);
      for (const action of editorialGuideActions[article.slug]) {
        expect(html).toContain(`href="${action.href.replaceAll("&", "&amp;")}"`);
        expect(html).toContain(action.label);
        expect(html).toContain(action.description);
      }
    }
  });

  it("renders lead photos and source attribution for adapted licensed articles", async () => {
    const adapted = editorialArticles.filter((article) => article.source);
    expect(adapted.length).toBeGreaterThanOrEqual(20);

    for (const article of adapted) {
      const html = renderToStaticMarkup(await ArticleDetailPage({ params: Promise.resolve({ slug: article.slug }) }));

      if (article.leadImage) {
        expect(html).toContain(`src="${article.leadImage.src}"`);
        expect(html).toContain(`alt="${article.leadImage.alt}"`);
      }
      expect(html).toContain("По материалам");
      expect(html).toContain(article.source!.url);
    }
  });

  it("connects the buyer guide to the collection hub and live used-car search", () => {
    expect(editorialGuideActions["pokupka-avtomobilya-s-probegom"].map(({ href }) => href)).toEqual([
      "/useful-information#use-case-presets-title",
      "/cars?category_code=cars&condition=used",
    ]);
    expect(editorialGuideActions["podgotovka-avtomobilya-k-prodazhe"].map(({ href }) => href)).toEqual([
      "/cars?category_code=cars&condition=used",
      "/sell",
    ]);
    expect(editorialGuideActions["kak-vybrat-avtoservis"].map(({ href }) => href)).toEqual(["/services"]);
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

  it("uses the lead photo in open graph metadata for adapted articles", async () => {
    const article = editorialArticles.find((item) => item.leadImage && item.source);
    if (!article) throw new Error("Expected an adapted article with a lead photo");

    const metadata = await generateMetadata({ params: Promise.resolve({ slug: article.slug }) });
    const rawImages = metadata.openGraph?.images;
    const imageList = rawImages == null ? [] : Array.isArray(rawImages) ? rawImages : [rawImages];
    const urls = imageList.map((image) => (typeof image === "string" ? image : "url" in image ? String(image.url) : ""));

    expect(urls.some((url) => url.includes(article.leadImage!.src))).toBe(true);
  });
});
