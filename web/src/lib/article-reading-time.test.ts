import { describe, expect, it } from "vitest";
import { articleReadingMinutes } from "./article-reading-time";
import type { EditorialArticle } from "./editorial-articles";

const empty: EditorialArticle = { slug: "test", title: "", section: "", description: "", sections: [], closingLabel: "", closingText: "" };

describe("article reading time", () => {
  it("shows at least one minute", () => {
    expect(articleReadingMinutes(empty)).toBe(1);
  });
  it("counts visible text at 1000 characters per minute, rounding up", () => {
    const article: EditorialArticle = { ...empty, sections: [{ heading: "", blocks: [
      { type: "paragraph", text: "а".repeat(500) },
      { type: "list", items: ["б".repeat(500)] },
      { type: "image", src: "x".repeat(1000), alt: "x".repeat(1000), caption: "в" },
    ] }] };
    expect(articleReadingMinutes(article)).toBe(2);
    expect(articleReadingMinutes({ ...empty, closingText: "а".repeat(1000) })).toBe(1);
  });
});
