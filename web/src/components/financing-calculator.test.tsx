import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { FinancingCalculator } from "@/components/financing-calculator";

it("keeps rate and fees under the user's control and collects no application details", () => {
  const page = renderToStaticMarkup(<FinancingCalculator initialPrice="120000" initialCurrency="BYN" initialMode="leasing" />);

  expect(page).toContain("Рассчитать платёж");
  expect(page).toContain("Данные формы никуда не отправляются");
  expect(page).toContain("Ставка в год, %");
  expect(page).toContain("Выкупной платёж");
  expect(page).toContain("делит введённую годовую ставку на 12 и использует аннуитетную схему");
  expect(page).toContain('value="120000"');
  expect(page).toContain('value="BYN"');
  expect(page).not.toContain('name="phone"');
  expect(page).not.toContain('name="email"');
  expect(page).not.toContain('name="name"');
  expect(page).not.toContain("<form");
});
