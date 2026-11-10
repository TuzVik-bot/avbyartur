import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it } from "vitest";
import { OwnershipCalculator } from "./ownership-calculator";

let root: Root;
let container: HTMLDivElement;
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  act(() => root.render(createElement(OwnershipCalculator)));
});
afterEach(() => { act(() => root.unmount()); container.remove(); });

function summary() { return container.querySelector('[aria-label="Краткий результат расчёта"]'); }
function setValue(name: string, value: string) {
  const input = container.querySelector<HTMLInputElement>(`[name="${name}"]`)!;
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

it("puts a live monthly estimate before the inputs and links to focusable detailed results", () => {
  expect(summary()).not.toBeNull();
  const shared = container.querySelector('[name="shared-years"]')!;
  expect(summary()!.compareDocumentPosition(shared) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  const link = summary()!.querySelector<HTMLAnchorElement>('a')!;
  const target = container.querySelector(link.getAttribute("href")!)!;
  expect(target.getAttribute("tabindex")).toBe("-1");
  const before = summary()!.querySelector("output")!.textContent;
  setValue("shared-annualKm", "30000");
  expect(summary()!.querySelector("output")!.textContent).not.toBe(before);
  expect(summary()!.querySelector("output")!.textContent).toBe(container.querySelector('[data-result="monthly"]')!.textContent);
});

it("does not leave a stale estimate when a required value is cleared", () => {
  expect(summary()).not.toBeNull();
  setValue("vehicle-0-priceByn", "");
  expect(summary()!.querySelector("output")).toBeNull();
  expect(summary()!.textContent).toContain("Уточните данные");
  expect(container.querySelector('[data-result="monthly"]')).toBeNull();
});

it("keeps both estimates and one results target when comparing vehicles", () => {
  expect(summary()).not.toBeNull();
  act(() => container.querySelector<HTMLButtonElement>('[data-action="add-vehicle"]')!.click());
  expect(summary()!.querySelectorAll("output")).toHaveLength(2);
  expect(container.querySelectorAll("#ownership-results")).toHaveLength(1);
  const target = container.querySelector("#ownership-results")!;
  expect(target.querySelector("input")).toBeNull();
  expect(target.querySelector('[data-result="monthly"]')).not.toBeNull();
});
