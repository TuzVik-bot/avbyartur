import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { SellerListings, type PublicSellerListing } from "@/components/seller-listings";
import { CompareProvider } from "@/components/compare-provider";

vi.mock("next/link", () => ({ default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a> }));
vi.mock("next/image", () => ({ default: ({ unoptimized: _unoptimized, priority: _priority, ...props }: React.ImgHTMLAttributes<HTMLImageElement> & { unoptimized?: boolean; priority?: boolean }) => <img {...props} /> }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/components/auth-provider", () => ({ useAuth: () => ({ user: null }) }));

const listing = (id: string, created_at = "2026-10-01T00:00:00Z"): PublicSellerListing => ({
  id, slug: id, title: id, status: "active", make: null, model: null, year: 2020, mileage_km: 10_000, fuel: "petrol", transmission: "manual", drive: "front",
  price: { amount: "1000", currency: "BYN" }, region: null, city: null, seller: { id: "seller-1", type: "private", name: "Продавец" }, created_at, updated_at: created_at, damaged: false, parts_only: false
});

describe("seller listings", () => {
  it("excludes current, other sellers, duplicates and returns at most eight in stable date order", () => {
    const items = [listing("current"), ...Array.from({ length: 10 }, (_, index) => listing(`item-${index}`, `2026-10-${String(index + 1).padStart(2, "0")}T00:00:00Z`)),
      { ...listing("other-seller"), seller: { id: "seller-2", type: "private" as const, name: "Другой" } }];
    const html = renderToStaticMarkup(createElement(CompareProvider, null, createElement(SellerListings, { listingId: "current", sellerId: "seller-1", items: [...items, items[1]] })));
    expect(html.match(/<article class="listing-card/g)).toHaveLength(8);
    expect(html).not.toContain(">current</a>");
    expect(html).not.toContain(">other-seller</a>");
    expect(html.indexOf("item-9")).toBeLessThan(html.indexOf("item-8"));
  });

  it("renders nothing when the seller has no other public listings", () => {
    const html = renderToStaticMarkup(createElement(CompareProvider, null, createElement(SellerListings, { listingId: "current", sellerId: "seller-1", items: [listing("current")] })));
    expect(html).toBe("");
  });
});
