import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ComparisonAction } from "@/components/comparison/comparison-action";
import { addComparisonId, clearComparisonIds } from "@/lib/comparison-state";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a>
}));

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  localStorage.clear();
  clearComparisonIds();
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  clearComparisonIds();
});

describe("comparison action", () => {
  it("adds and removes a listing and keeps the selected list one click away", async () => {
    await act(async () => root.render(<ComparisonAction listingId="one" />));
    const toggle = container.querySelector<HTMLButtonElement>("button")!;

    expect(toggle.getAttribute("aria-pressed")).toBe("false");
    expect(container.querySelector('a[href="/compare"]')?.textContent).toBe("Сравнение");
    await act(async () => toggle.click());
    expect(toggle.getAttribute("aria-pressed")).toBe("true");
    expect(container.querySelector('a[href="/compare"]')?.textContent).toBe("Сравнение (1)");
    expect(localStorage.getItem("avtorinok:comparison")).toBe('["one"]');

    await act(async () => toggle.click());
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
    expect(container.querySelector('a[href="/compare"]')?.textContent).toBe("Сравнение");
  });

  it("explains when the four listing selection is full", async () => {
    ["one", "two", "three", "four"].forEach((id) => addComparisonId(id));
    await act(async () => root.render(<ComparisonAction listingId="five" />));

    const toggle = container.querySelector<HTMLButtonElement>("button")!;
    expect(toggle.disabled).toBe(true);
    expect(container.textContent).toContain("Можно выбрать не больше 4 объявлений");
    expect(container.querySelector('a[href="/compare"]')?.textContent).toBe("Сравнение (4)");
  });
});
