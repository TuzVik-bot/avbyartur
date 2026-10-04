import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import PromotionPage, { metadata } from "./page";

describe("promotion page", () => {
  it("explains that paid promotion is unavailable in the closed pilot", () => {
    const html = renderToStaticMarkup(<PromotionPage />);

    expect(metadata.title).toBe("Продвижение объявлений");
    expect(html).toContain("Продвижение объявлений");
    expect(html).toContain("Продвижение, тарифы, платежи и callbacks пока не реализованы");
    expect(html).toContain('href="/sell"');
    expect(html).toContain('href="/help"');
    expect(html).not.toMatch(/\b(?:BYN|USD|руб(?:лей|\.)?)\b/i);
    expect(html).not.toContain("<button");
    expect(html).not.toMatch(/href="[^"]*(?:payment|checkout|tariff)/i);
  });
});
