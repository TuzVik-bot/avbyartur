import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { MarketBadge } from "@/components/market-badge";

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

const base = { median_byn: "25000.00", sample_size: 12, seller_count: 6, as_of: "2026-10-25", rate_date: null };

describe("market badge", () => {
  it("labels a below-market price with the median tooltip", async () => {
    await act(async () => {
      root.render(createElement(MarketBadge, { comparison: { ...base, label: "below_market" as const } }));
    });
    const badge = container.querySelector<HTMLElement>("[data-market-comparison]")!;
    expect(badge.textContent).toBe("Цена ниже рынка");
    expect(badge.className).toContain("below_market");
    expect(badge.getAttribute("title")).toContain(`25\u00A0000 BYN`);
    expect(badge.getAttribute("title")).toContain("12 объявлениям");
  });

  it("labels an above-market price", async () => {
    await act(async () => {
      root.render(createElement(MarketBadge, { comparison: { ...base, label: "above_market" as const } }));
    });
    const badge = container.querySelector<HTMLElement>("[data-market-comparison]")!;
    expect(badge.textContent).toBe("Цена выше рынка");
    expect(badge.className).toContain("above_market");
  });
});
