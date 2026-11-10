import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MarketPriceHint } from "@/components/market-price-hint";

function render(comparison: Parameters<typeof MarketPriceHint>[0]["comparison"]) {
  return renderToStaticMarkup(createElement(MarketPriceHint, { listingId: "listing-1", comparison }));
}

describe("owner market price hint", () => {
  it("shows the signed gap for prices above and below the market", () => {
    expect(render({ label: "above_market", difference_percent: 20 })).toContain("Цена выше рынка на 20%");
    expect(render({ label: "below_market", difference_percent: -15 })).toContain("Цена ниже рынка на 15%");
  });

  it("tells the owner the price is in the market without a percentage", () => {
    const html = render({ label: "in_market", difference_percent: 3 });

    expect(html).toContain("Цена в рынке");
    expect(html).not.toContain("%");
    expect(html).toContain('class="market-badge in_market"');
    expect(html).toContain('href="/sell?listing=listing-1"');
  });

  it("renders nothing without comparison data", () => {
    expect(render(null)).toBe("");
    expect(render(undefined)).toBe("");
  });
});
