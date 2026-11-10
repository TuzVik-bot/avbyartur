import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import PromotionPage, { metadata } from "./page";

describe("promotion page", () => {
  it("describes supported formats and current restrictions", () => {
    const html = renderToStaticMarkup(<PromotionPage />);
    expect(metadata.title).toBe("Продвижение объявлений");
    expect(html).toContain("Заказ и оплата недоступны");
    expect(html).toContain("Поднять объявление");
    expect(html).toContain("Выделить объявление");
    expect(html).toContain("Разместить вверху");
    expect(html).toContain("PRO");
    expect(html).toContain("сохранить его как черновик и добавить фотографии");
    expect(html).toContain("актуальный статус в кабинете");
    expect(html).toContain("снять с публикации или отметить продажу");
    expect(html).not.toMatch(/премодераци/i);
    expect(html).not.toContain("Срочно");
    expect(html).toContain('href="/account/billing"');
    expect(html).toContain('href="/sell"');
    expect(html).toContain('href="/help"');
    expect(html).not.toMatch(/\b(?:BYN|USD|руб(?:лей|\.)?)\b/i);
    expect(html).not.toContain("<button");
    expect(html).not.toMatch(/href="[^"]*(?:payment|checkout)/i);
  });
});
