import { renderToStaticMarkup } from "react-dom/server";
import { act } from "react";
import { createRoot } from "react-dom/client";
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

function calculateInBrowser(fees: string) {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  act(() => root.render(<FinancingCalculator initialPrice="1" />));
  const fill = (label: string, value: string) => {
    const field = Array.from(container.querySelectorAll("label")).find(item => item.textContent?.includes(label))!.querySelector("input")!;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(field, value);
    field.dispatchEvent(new Event("input", { bubbles: true }));
  };
  act(() => { fill("Аванс", "0"); fill("Срок, месяцев", "3"); fill("Ставка в год", "0"); fill("Известные комиссии", fees); });
  act(() => container.querySelector<HTMLButtonElement>(".form-actions button")!.click());
  return { container, cleanup: () => { act(() => root.unmount()); container.remove(); } };
}

it("shows the final rounding adjustment and the exact total for a one-ruble zero-interest loan", () => {
  const { container, cleanup } = calculateInBrowser("0");
  try {
    const finalRow = Array.from(container.querySelectorAll("dl div")).find(item => item.textContent?.includes("Последний платёж"));
    expect(finalRow?.querySelector("dd")?.textContent).toContain("0,34");
    const totalRow = Array.from(container.querySelectorAll("dl div")).find(item => item.textContent?.includes("Всего с авансом"));
    expect(totalRow?.querySelector("dd")?.textContent).toContain("1,00");
    expect(container.textContent).toContain("Последний платёж корректируется");
  } finally { cleanup(); }
});

it("shows an input error instead of an infinite result for extreme finite commissions", () => {
  const { container, cleanup } = calculateInBrowser(String(Number.MAX_VALUE));
  try {
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("Комиссии должны быть");
    expect(container.querySelector(".financing-result")).toBeNull();
    expect(container.textContent).not.toContain("∞");
  } finally { cleanup(); }
});
