import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import ProSubscriptionPage, { metadata } from "./page";

describe("pro subscription page", () => {
  it("describes company capabilities without inventing payment availability", () => {
    const html = renderToStaticMarkup(<ProSubscriptionPage />);
    expect(metadata.title).toBe("Pro для компаний");
    expect(html).toContain("Создать заказ и оплатить подписку сейчас нельзя");
    expect(html).toContain("активные настроенные предложения, если они есть");
    expect(html).toContain("Базовый профиль компании и публичная страница");
    expect(html).toContain("Ручная подача объявлений");
    expect(html).toContain("текущих статусов объявлений в кабинете");
    expect(html).toContain("Управление командой компании: сотрудники и их роли в кабинете");
    expect(html).toContain("Аналитика объявлений с отдельными счётчиками просмотров");
    expect(html).toContain("не связывают действия одного посетителя");
    expect(html).not.toMatch(/премодераци|отправки на модерацию/i);
    expect(html).toContain('href="/account/billing"');
    expect(html).toContain('href="/account/company"');
    expect(html).toContain('href="/dealers"');
    expect(html).not.toMatch(/\b(?:BYN|USD|руб(?:лей|\.)?)\b/i);
    expect(html).not.toContain("<button");
    expect(html).not.toMatch(/href="[^"]*(?:payment|checkout|tariff)/i);
  });
});
