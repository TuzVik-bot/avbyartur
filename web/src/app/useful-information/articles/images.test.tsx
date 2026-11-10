import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import ArticlesPage from "@/app/useful-information/articles/page";
import ArticleDetailPage from "@/app/useful-information/articles/[slug]/page";
import { editorialArticles } from "@/lib/editorial-articles";

function images(html: string) {
  return html.match(/<img [^>]*>/g) ?? [];
}

describe("editorial image loading", () => {
  it("loads only the first article thumbnail eagerly and reserves space for every one", () => {
    const tags = images(renderToStaticMarkup(<ArticlesPage />));

    expect(tags.length).toBeGreaterThan(1);
    expect(tags[0]).toContain('loading="eager"');
    for (const tag of tags) {
      expect(tag).toMatch(/width="\d+"/);
      expect(tag).toMatch(/height="\d+"/);
      expect(tag).toContain('decoding="async"');
    }
    for (const tag of tags.slice(1)) expect(tag).toContain('loading="lazy"');
  });

  it("keeps the hero eager and lazy-loads body photos of an article", async () => {
    const article = editorialArticles.find((item) => item.leadImage && item.sections.some((section) => section.blocks.some((block) => block.type === "image")));
    if (!article) throw new Error("Expected an article with a lead image and body photos");

    const tags = images(renderToStaticMarkup(await ArticleDetailPage({ params: Promise.resolve({ slug: article.slug }) })));

    expect(tags[0]).not.toContain('loading="lazy"');
    expect(tags[0]).toMatch(/fetchPriority="high"|fetchpriority="high"/);
    expect(tags.length).toBeGreaterThan(1);
    for (const tag of tags) {
      expect(tag).toMatch(/width="\d+"/);
      expect(tag).toMatch(/height="\d+"/);
      expect(tag).toContain('decoding="async"');
    }
    for (const tag of tags.slice(1)) expect(tag).toContain('loading="lazy"');
  });
});
