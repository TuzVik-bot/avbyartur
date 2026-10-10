import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import FinancingPage, { metadata } from "@/app/financing/page";

it("prefills only validated price, currency, and financing mode query values", async () => {
  const valid = renderToStaticMarkup(await FinancingPage({
    searchParams: Promise.resolve({ price: "12000.50", currency: "EUR", mode: "leasing" })
  }));
  expect(valid).toContain('value="12000.50"');
  expect(valid).toContain('<option value="EUR" selected="">EUR</option>');
  expect(valid).toContain('<option value="leasing" selected="">Лизинг</option>');
  expect(valid).not.toContain("listing-1");

  const invalid = renderToStaticMarkup(await FinancingPage({
    searchParams: Promise.resolve({ price: "1e999", currency: "RUB", mode: "unknown" })
  }));
  expect(invalid).toContain('value=""');
  expect(invalid).toContain('<option value="BYN" selected="">BYN</option>');
  expect(invalid).toContain('<option value="credit" selected="">Кредит</option>');
});

it("keeps the financing page out of search indexes", () => {
  expect(metadata.robots).toEqual({ index: false, follow: false, noarchive: true, googleBot: { index: false, follow: false, noimageindex: true } });
});
