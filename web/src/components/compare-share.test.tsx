import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CompareButton } from "@/components/compare-button";
import { COMPARE_STORAGE_KEY, CompareProvider, MAX_COMPARE_LISTINGS, parseCompareIds } from "@/components/compare-provider";
import { ShareButton } from "@/components/share-button";

let root: Root;
let container: HTMLDivElement;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  localStorage.clear();
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function renderButtons(ids: string[]) {
  act(() => root.render(<CompareProvider>{ids.map((id) => <CompareButton key={id} listingId={id} />)}</CompareProvider>));
}

function buttons() { return [...container.querySelectorAll<HTMLButtonElement>("button")]; }

describe("compare list", () => {
  it("parses only unique non-empty ids and tolerates corrupt storage", () => {
    expect(parseCompareIds("not-json")).toEqual([]);
    expect(parseCompareIds(JSON.stringify(["a", "", 2, "a", "b", "c", "d", "e"]))).toEqual(["a", "b", "c", "d"]);
    expect(MAX_COMPARE_LISTINGS).toBe(4);
  });

  it("persists four unique selections and announces when a fifth is refused", () => {
    renderButtons(["one", "two", "three", "four", "five"]);
    for (const button of buttons().slice(0, 4)) act(() => button.click());
    expect(localStorage.getItem(COMPARE_STORAGE_KEY)).toBe(JSON.stringify(["one", "two", "three", "four"]));
    act(() => buttons()[4].click());
    expect(container.textContent).toContain("Сравнение (4)");
    expect(container.textContent).toContain("не больше четырёх");
    expect(localStorage.getItem(COMPARE_STORAGE_KEY)).toBe(JSON.stringify(["one", "two", "three", "four"]));
  });

  it("does not duplicate an id and restores saved ids after remount", () => {
    localStorage.setItem(COMPARE_STORAGE_KEY, JSON.stringify(["one", "one", "two"]));
    renderButtons(["one", "two", "three"]);
    expect(buttons()[0].getAttribute("aria-pressed")).toBe("true");
    expect(container.textContent).toContain("Сравнение (2)");
    act(() => buttons()[0].click());
    expect(localStorage.getItem(COMPARE_STORAGE_KEY)).toBe(JSON.stringify(["two"]));
  });

  it("continues to work for this tab when localStorage is unavailable", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("Blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("Blocked"); });
    renderButtons(["one"]);
    act(() => buttons()[0].click());
    expect(container.textContent).toContain("Сравнение (1)");
  });
});

describe("share button", () => {
  it("copies the absolute canonical URL when Web Share is unavailable", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    act(() => root.render(<ShareButton href="/cars/a/b/123" title="Автомобиль" />));
    await act(async () => { buttons()[0].click(); await Promise.resolve(); });
    expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/cars/a/b/123`);
    expect(container.textContent).toContain("Ссылка скопирована.");
  });

  it("treats a cancelled native share as cancellation, not an error", async () => {
    const share = vi.fn().mockRejectedValue(Object.assign(new Error("cancelled"), { name: "AbortError" }));
    Object.defineProperty(navigator, "share", { configurable: true, value: share });
    act(() => root.render(<ShareButton href="/cars/a/b/123" title="Автомобиль" />));
    await act(async () => { buttons()[0].click(); await Promise.resolve(); });
    expect(share).toHaveBeenCalledWith({ title: "Автомобиль", url: `${window.location.origin}/cars/a/b/123` });
    expect(container.querySelector('[role="status"]')?.textContent).toBe("");
  });
});
