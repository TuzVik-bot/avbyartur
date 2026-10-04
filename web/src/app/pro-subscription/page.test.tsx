import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import ProSubscriptionPage, { metadata } from "./page";

describe("pro subscription page", () => {
  it("describes the draft status without inventing a plan or payment flow", () => {
    const html = renderToStaticMarkup(<ProSubscriptionPage />);

    expect(metadata.title).toBe("Pro для компаний");
    expect(html).toContain("Тарифы, счета, платежи и управление подпиской пока не реализованы");
    expect(html).toContain("Командные роли и управление сотрудниками компании");
    expect(html).toContain('href="/account/company"');
    expect(html).toContain('href="/dealers"');
    expect(html).not.toMatch(/\b(?:BYN|USD|руб(?:лей|\.)?)\b/i);
    expect(html).not.toContain("<button");
    expect(html).not.toMatch(/href="[^"]*(?:payment|checkout|tariff)/i);
  });
});
