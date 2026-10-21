import { cache } from "react";
import { ARTICLE_TOPIC_LABELS, type ArticlePublicItem, type ArticleSummary } from "@/lib/content";
import { contentServerApi } from "@/lib/content-server";
import { editorialArticles } from "@/lib/editorial-articles";

const PAGE_SIZE = 100;
const MAX_PAGES = 10;
const ARTICLE_SLUG_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const MAX_SLUG_LENGTH = 100;

export type ArticleCard = {
  slug: string;
  title: string;
  section: string;
  description: string;
  origin: "static" | "managed";
};

function toManagedCard(item: ArticleSummary): ArticleCard {
  return {
    slug: item.slug,
    title: item.title,
    section: ARTICLE_TOPIC_LABELS[item.topic] ?? "Полезная информация",
    description: item.summary,
    origin: "managed",
  };
}

/** Published managed article summaries, newest first. Never throws: an unavailable API yields an empty list. */
export async function loadManagedArticleSummaries(): Promise<ArticleSummary[]> {
  try {
    const items: ArticleSummary[] = [];
    for (let page = 1; page <= MAX_PAGES; page += 1) {
      const response = await contentServerApi.articles(undefined, page, PAGE_SIZE);
      items.push(...response.items);
      if (items.length >= response.total || response.items.length === 0) break;
    }
    return items;
  } catch {
    return [];
  }
}

/** One published managed article, or null when it is absent, unpublished, malformed, or the API is unavailable. Memoized per request. */
export const loadManagedArticle = cache(async (slug: string): Promise<ArticlePublicItem | null> => {
  if (slug.length > MAX_SLUG_LENGTH || !ARTICLE_SLUG_PATTERN.test(slug)) return null;
  try {
    const { content } = await contentServerApi.article(slug);
    return content.kind === "article" && content.status === "published" && content.key === slug ? content : null;
  } catch {
    return null;
  }
});

/** Managed cards first (API order), then static ones; a static slug always wins a collision. */
export function mergeArticleCards(managed: readonly ArticleSummary[]): ArticleCard[] {
  const staticCards: ArticleCard[] = editorialArticles.map(({ slug, title, section, description }) => (
    { slug, title, section, description, origin: "static" }
  ));
  const staticSlugs = new Set(staticCards.map((card) => card.slug));
  const seen = new Set<string>();
  const managedCards: ArticleCard[] = [];
  for (const item of managed) {
    if (staticSlugs.has(item.slug) || seen.has(item.slug)) continue;
    seen.add(item.slug);
    managedCards.push(toManagedCard(item));
  }
  return [...managedCards, ...staticCards];
}

export async function loadArticleCards(): Promise<ArticleCard[]> {
  return mergeArticleCards(await loadManagedArticleSummaries());
}

/** Plain-text body to paragraphs; no markup is ever interpreted. */
export function splitArticleParagraphs(body: string): string[] {
  return body.split(/\n\s*\n/).map((part) => part.trim()).filter(Boolean);
}
