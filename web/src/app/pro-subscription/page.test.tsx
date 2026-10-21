import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import ProSubscriptionPage, { metadata } from "./page";

describe("pro subscription page", () => {
  it("describes the draft status without inventing a plan or payment flow", () => {
    const html = renderToStaticMarkup(<ProSubscriptionPage />);

    expect(metadata.title).toBe("Pro для компаний");
    expect(html).toContain("Создать заказ и оплатить подписку сейчас нельзя");
    expect(html).toContain("состав и стоимость ещё не утверждены");
    expect(html).toContain("Управление командой компании: сотрудники и их роли в кабинете");
    expect(html).toContain("Аналитика объявлений с отдельными счётчиками просмотров");
    expect(html).toContain("не связывают действия одного посетителя");
    expect(html).not.toContain("следующему этапу");
    expect(html).toContain('href="/account/billing"');
    expect(html).toContain('href="/account/company"');
    expect(html).toContain('href="/dealers"');
    expect(html).not.toMatch(/\b(?:BYN|USD|руб(?:лей|\.)?)\b/i);
    expect(html).not.toContain("<button");
    expect(html).not.toMatch(/href="[^"]*(?:payment|checkout|tariff)/i);
  });
});
