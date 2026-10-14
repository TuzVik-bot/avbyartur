import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import UsefulInformationPage from "@/app/useful-information/page";
import CheckCarBeforeBuyingPage from "@/app/useful-information/check-car-before-buying/page";
import { metadata as checkCarMetadata } from "@/app/useful-information/check-car-before-buying/page";

describe("useful information pages", () => {
  it("links the useful-information index to the practical car inspection guide", () => {
    const html = renderToStaticMarkup(<UsefulInformationPage />);

    expect(html).toContain("Как проверить авто перед покупкой");
    expect(html).toContain('href="/useful-information/check-car-before-buying"');
  });

  it("renders a dated buying checklist with official services and existing tools", () => {
    const html = renderToStaticMarkup(<CheckCarBeforeBuyingPage />);

    expect(html).toContain("Сверьте документы и данные продавца");
    expect(html).toContain("3.58.01");
    expect(html).toContain("3.59.01");
    expect(html).toContain("проверке, находится ли транспортное средство в розыске, по полному совпадению VIN");
    expect(html).toContain("3.62.01");
    expect(html).toContain("3.68.01");
    expect(html).toContain('href="https://e-pasluga.by/services/gai-transport"');
    expect(html).toContain('href="/vin-check"');
    expect(html).toContain('href="/customs-calculator"');
    expect(html).toContain('href="/sale-contract"');
    expect(html).toContain("Проверено 15 октября 2026 года");
    expect(html).toContain("не принимаем и не сохраняем VIN");
    expect(html).toContain("поставщик отчётов не подключён");
    expect(html).not.toMatch(/<form|<input/i);
    expect(checkCarMetadata.alternates).toEqual({ canonical: "/useful-information/check-car-before-buying" });
  });
});
