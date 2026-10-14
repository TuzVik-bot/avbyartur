import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CatalogDisplay } from "./catalog-display";

let container: HTMLDivElement;
let root: Root;
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  localStorage.clear();
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});
afterEach(() => { act(() => root.unmount()); container.remove(); vi.restoreAllMocks(); });

async function render() {
  await act(async () => root.render(<CatalogDisplay entries={[]} savedListingIds={[]} count={<strong>Объявления</strong>} controls={<select aria-label="Сортировка"><option>Сначала новые</option></select>} emptyState={<p>Нет объявлений</p>} />));
}

it("switches display without navigation and restores the choice on remount", async () => {
  await render();
  expect(container.querySelector('[aria-label="Список"]')?.getAttribute("aria-pressed")).toBe("true");
  const grid = container.querySelector<HTMLButtonElement>('[aria-label="Сетка"]');
  expect(grid).not.toBeNull();
  await act(async () => grid!.click());
  expect(grid!.getAttribute("aria-pressed")).toBe("true");
  expect(localStorage.getItem("avtorinok:catalog-view")).toBe("grid");
  act(() => root.unmount());
  root = createRoot(container);
  await render();
  expect(container.querySelector('[aria-label="Сетка"]')?.getAttribute("aria-pressed")).toBe("true");
  await act(async () => container.querySelector<HTMLButtonElement>('[aria-label="Список"]')!.click());
  expect(localStorage.getItem("avtorinok:catalog-view")).toBe("row");
  expect(container.querySelector('[aria-label="Сортировка"]')).not.toBeNull();
});

it("keeps display switching usable when browser storage is unavailable", async () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
  await render();
  const grid = container.querySelector<HTMLButtonElement>('[aria-label="Сетка"]');
  expect(grid).not.toBeNull();
  await act(async () => grid!.click());
  expect(grid!.getAttribute("aria-pressed")).toBe("true");
});
