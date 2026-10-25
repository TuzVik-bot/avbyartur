import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CompareButton } from "@/components/compare-button";
import { COMPARE_STORAGE_KEY, CompareProvider, MAX_COMPARE_LISTINGS, parseCompareIds } from "@/components/compare-provider";
import { ShareButton } from "@/components/share-button";
import { ListingCard } from "@/components/listing-card";
import type { ListingSummary } from "@/lib/types";

vi.mock("next/link", () => ({ default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a> }));
vi.mock("next/image", () => ({ default: ({ unoptimized: _unoptimized, priority: _priority, ...props }: React.ImgHTMLAttributes<HTMLImageElement> & { unoptimized?: boolean; priority?: boolean }) => <img {...props} /> }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));
vi.mock("@/components/auth-provider", () => ({ useAuth: () => ({ user: null }) }));

const listing: ListingSummary = {
  id: "listing-card-1", slug: "listing-card-1", title: "Марка Модель",
  make: { id: "make-1", slug: "marka", name: "Марка" }, model: { id: "model-1", slug: "model", name: "Модель" },
  year: 2020, mileage_km: 50_000, fuel: "petrol", transmission: "manual", drive: "front",
  price: { amount: "10000", currency: "BYN" }, region: null, city: null,
  seller: { id: "seller-1", type: "private", name: "Продавец" }, created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-01T00:00:00Z", damaged: false, parts_only: false
};

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
  it("integrates the compare control into a listing card", async () => {
    act(() => root.render(<CompareProvider><ListingCard listing={listing} /></CompareProvider>));
    await act(async () => { await Promise.resolve(); });

    const button = container.querySelector<HTMLButtonElement>(".compare-action button")!;
    expect(button.getAttribute("aria-pressed")).toBe("false");
    await act(async () => { button.click(); await Promise.resolve(); });

    expect(button.getAttribute("aria-pressed")).toBe("true");
    expect(localStorage.getItem(COMPARE_STORAGE_KEY)).toBe(JSON.stringify([listing.id]));
    expect(container.querySelector('.compare-action a[href="/compare"]')?.textContent).toContain("Сравнение (1)");
  });

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
