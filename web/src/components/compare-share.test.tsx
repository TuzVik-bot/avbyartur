import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MAX_COMPARE_LISTINGS, parseCompareIds } from "@/components/compare-provider";
import { ShareButton } from "@/components/share-button";

vi.mock("next/link", () => ({ default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a> }));
vi.mock("next/image", () => ({ default: ({ unoptimized: _unoptimized, priority: _priority, ...props }: React.ImgHTMLAttributes<HTMLImageElement> & { unoptimized?: boolean; priority?: boolean }) => <img {...props} /> }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));
vi.mock("@/components/auth-provider", () => ({ useAuth: () => ({ user: null }) }));

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

function buttons() { return [...container.querySelectorAll<HTMLButtonElement>("button")]; }

describe("compare list", () => {
  it("parses only unique non-empty ids and tolerates corrupt storage", () => {
    expect(parseCompareIds("not-json")).toEqual([]);
    expect(parseCompareIds(JSON.stringify(["a", "", 2, "a", "b", "c", "d", "e"]))).toEqual(["a", "b", "c", "d"]);
    expect(MAX_COMPARE_LISTINGS).toBe(4);
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
