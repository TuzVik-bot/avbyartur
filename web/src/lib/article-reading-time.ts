import type { EditorialArticle } from "./editorial-articles";

/** Approximate reading time at 1000 visible characters per minute. */
export function articleReadingMinutes(article: EditorialArticle): number {
  const text = [
    article.title, article.description, article.leadImage?.caption ?? "",
    ...article.sections.flatMap((section) => [section.heading, ...section.blocks.flatMap((block) =>
      block.type === "paragraph" ? [block.text] : block.type === "list" ? [...block.items] : [block.caption ?? ""])]),
    article.closingLabel, article.closingText,
  ].filter(Boolean).join(" ").replace(/\s+/g, " ").trim();
  return Math.max(1, Math.ceil(Array.from(text).length / 1000));
}
