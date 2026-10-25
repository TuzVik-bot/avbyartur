import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import PromotionPage, { metadata } from "./page";

describe("promotion page", () => {
  it("explains that paid promotion is unavailable in the closed pilot", () => {
    const html = renderToStaticMarkup(<PromotionPage />);

    expect(metadata.title).toBe("Продвижение объявлений");
    expect(html).toContain("Продвижение объявлений");
    expect(html).toContain("Сейчас заказ и оплата недоступны");
    expect(html).toContain("Перечень включает четыре вида продвижения");
    expect(html).toContain("Поднять в топ");
    expect(html).toContain("Выделить");
    expect(html).toContain("Срочно");
    expect(html).toContain("PRO");
    expect(html).toContain('href="/account/billing"');
    expect(html).toContain('href="/sell"');
    expect(html).toContain('href="/help"');
    expect(html).not.toMatch(/\b(?:BYN|USD|руб(?:лей|\.)?)\b/i);
    expect(html).not.toContain("<button");
    expect(html).not.toMatch(/href="[^"]*(?:payment|checkout)/i);
  });
});
