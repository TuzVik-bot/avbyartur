import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RecentlyViewedListings } from "@/components/recently-viewed-listings";
import { api } from "@/lib/api";
import {
  readRecentlyViewedListingIds,
  recordRecentlyViewedListing,
} from "@/lib/recently-viewed";
import type { ListingSummary } from "@/lib/types";

const mocks = vi.hoisted(() => ({ recentListings: vi.fn() }));

vi.mock("@/lib/api", () => ({
  api: { recentListings: mocks.recentListings },
  ApiClientError: class ApiClientError extends Error { status = 500; }
}));
vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a>
}));
vi.mock("next/image", () => ({
  default: ({ unoptimized: _unoptimized, priority: _priority, ...props }: React.ImgHTMLAttributes<HTMLImageElement> & { unoptimized?: boolean; priority?: boolean }) => <img {...props} />
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));
vi.mock("@/components/auth-provider", () => ({ useAuth: () => ({ user: null }) }));

const currentId = "00000000-0000-4000-8000-000000000003";
const firstId = "00000000-0000-4000-8000-000000000001";
const secondId = "00000000-0000-4000-8000-000000000002";
const userId = "00000000-0000-4000-8000-000000000100";

function listing(id: string, title: string): ListingSummary {
  return {
    id,
    slug: id,
    title,
    make: { id: "make-1", slug: "mazda", name: "Mazda" },
    model: { id: "model-1", slug: "3", name: "3" },
    year: 2020,
    mileage_km: 50000,
    fuel: "petrol",
    transmission: "manual",
    drive: "front",
    price: { amount: "10000", currency: "BYN" },
    region: { id: "region-1", slug: "minsk", name: "Минская область" },
    city: { id: "city-1", slug: "minsk", name: "Минск" },
    seller: { id: "seller-1", type: "private", name: "Продавец" },
    created_at: "2026-10-20T00:00:00Z",
    updated_at: "2026-10-20T00:00:00Z",
    damaged: false,
    parts_only: false,
  };
}

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  localStorage.clear();
  mocks.recentListings.mockReset();
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

describe("recently viewed listings", () => {
  it("revalidates prior IDs, lets the visitor remove and clear history, and hides another account's history after sign-out", async () => {
    const now = Date.now();
    recordRecentlyViewedListing(firstId, userId, now - 2000);
    recordRecentlyViewedListing(secondId, userId, now - 1000);
    mocks.recentListings.mockResolvedValue({ items: [listing(secondId, "Mazda 3 newer"), listing(firstId, "Mazda 3 older")] });

    await act(async () => {
      root.render(createElement(RecentlyViewedListings, {
        currentListingId: currentId,
        userId,
        shouldRecord: true,
      }));
    });

    expect(mocks.recentListings).toHaveBeenCalledWith([currentId, secondId, firstId].filter((id) => id !== currentId));
    expect(container.querySelectorAll(".listing-card")).toHaveLength(2);
    expect(container.querySelectorAll(".card-title")[0]?.textContent).toBe("Mazda 3 newer");
    expect(readRecentlyViewedListingIds(userId, now + 2000)).toEqual([currentId, secondId, firstId]);

    await act(async () => {
      container.querySelector<HTMLButtonElement>(`button[aria-label="Удалить из недавно просмотренных: Mazda 3 newer"]`)!.click();
    });
    expect(readRecentlyViewedListingIds(userId, now + 2000)).toEqual([currentId, firstId]);
    expect(container.querySelectorAll(".listing-card")).toHaveLength(1);

    await act(async () => {
      container.querySelector<HTMLButtonElement>(`button[aria-label="Очистить историю недавно просмотренных объявлений"]`)!.click();
    });
    expect(readRecentlyViewedListingIds(userId, now + 2000)).toEqual([]);
    expect(container.querySelector("section[aria-labelledby='recent-listings-heading']")).toBeNull();

    mocks.recentListings.mockResolvedValue({ items: [listing(firstId, "Mazda 3 older")] });
    recordRecentlyViewedListing(firstId, userId, now);
    await act(async () => {
      root.render(createElement(RecentlyViewedListings, {
        currentListingId: currentId,
        userId: null,
        shouldRecord: false,
      }));
    });
    expect(container.querySelector(".listing-card")).toBeNull();
    expect(mocks.recentListings).toHaveBeenCalledTimes(1);
  });

  it("does not render an empty section when none of the saved IDs remain public", async () => {
    const now = Date.now();
    recordRecentlyViewedListing(firstId, null, now);
    mocks.recentListings.mockResolvedValue({ items: [] });

    await act(async () => {
      root.render(createElement(RecentlyViewedListings, {
        currentListingId: currentId,
        userId: null,
        shouldRecord: true,
      }));
    });

    expect(container.querySelector("section[aria-labelledby='recent-listings-heading']")).toBeNull();
  });

  it("discards an older account response after the account changes", async () => {
    let resolveAccountA!: (value: { items: ListingSummary[] }) => void;
    const accountAResponse = new Promise<{ items: ListingSummary[] }>((resolve) => { resolveAccountA = resolve; });
    mocks.recentListings
      .mockReturnValueOnce(accountAResponse)
      .mockResolvedValueOnce({ items: [listing(secondId, "Account B history")] });
    const accountA = "00000000-0000-4000-8000-000000000101";
    const accountB = "00000000-0000-4000-8000-000000000102";
    recordRecentlyViewedListing(firstId, accountA);
    recordRecentlyViewedListing(secondId, accountB);

    await act(async () => {
      root.render(createElement(RecentlyViewedListings, {
        currentListingId: currentId,
        userId: accountA,
        shouldRecord: false,
      }));
    });
    expect(container.querySelector(".listing-card")).toBeNull();

    await act(async () => {
      root.render(createElement(RecentlyViewedListings, {
        currentListingId: currentId,
        userId: accountB,
        shouldRecord: false,
      }));
    });
    expect(container.textContent).toContain("Account B history");

    await act(async () => {
      resolveAccountA({ items: [listing(firstId, "Account A history")] });
      await accountAResponse;
    });
    expect(container.textContent).toContain("Account B history");
    expect(container.textContent).not.toContain("Account A history");
  });
});
