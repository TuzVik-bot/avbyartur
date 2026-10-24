import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  MAX_RECENT_LISTINGS,
  RECENT_LISTINGS_TTL_MS,
  clearRecentlyViewedListings,
  readRecentlyViewedListingIds,
  recordRecentlyViewedListing,
  recentlyViewedStorageKey,
  removeRecentlyViewedListing,
} from "@/lib/recently-viewed";

const makeId = (value: number) => `00000000-0000-4000-8000-${String(value).padStart(12, "0")}`;
const accountId = "11111111-1111-4111-8111-111111111111";

beforeEach(() => localStorage.clear());

describe("recently viewed listing storage", () => {
  it("records only actual visits, orders newest first, and enforces the bounded limit", () => {
    const now = Date.UTC(2026, 9, 21);
    expect(recordRecentlyViewedListing(makeId(1), null, now)).toEqual([]);
    expect(recordRecentlyViewedListing(makeId(2), null, now + 1000)).toEqual([makeId(1)]);

    for (let value = 3; value <= MAX_RECENT_LISTINGS + 4; value += 1) {
      recordRecentlyViewedListing(makeId(value), null, now + value * 1000);
    }

    const ids = readRecentlyViewedListingIds(null, now + 20_000);
    expect(ids).toHaveLength(MAX_RECENT_LISTINGS);
    expect(ids[0]).toBe(makeId(MAX_RECENT_LISTINGS + 4));
    expect(ids).not.toContain(makeId(1));
  });

  it("expires old entries without refreshing their visit time", () => {
    const now = Date.UTC(2026, 9, 21);
    localStorage.setItem(recentlyViewedStorageKey(null), JSON.stringify([
      { id: makeId(1), viewedAt: now - RECENT_LISTINGS_TTL_MS - 1 },
      { id: makeId(2), viewedAt: now - RECENT_LISTINGS_TTL_MS + 1 },
      { id: "not-a-uuid", viewedAt: now },
      { id: makeId(3), viewedAt: now + 10_000_000 },
    ]));

    expect(readRecentlyViewedListingIds(null, now)).toEqual([makeId(2)]);
    expect(JSON.parse(localStorage.getItem(recentlyViewedStorageKey(null)) || "[]")).toEqual([
      { id: makeId(2), viewedAt: now - RECENT_LISTINGS_TTL_MS + 1 },
    ]);
  });

  it("keeps guest and account histories separate and supports removal and clearing", () => {
    const now = Date.UTC(2026, 9, 21);
    recordRecentlyViewedListing(makeId(1), null, now);
    recordRecentlyViewedListing(makeId(2), accountId, now);

    expect(readRecentlyViewedListingIds(null, now)).toEqual([makeId(1)]);
    expect(readRecentlyViewedListingIds(accountId, now)).toEqual([makeId(2)]);

    removeRecentlyViewedListing(accountId, makeId(2), now);
    expect(readRecentlyViewedListingIds(accountId, now)).toEqual([]);
    clearRecentlyViewedListings(accountId);
    expect(localStorage.getItem(recentlyViewedStorageKey(accountId))).toBeNull();
    expect(readRecentlyViewedListingIds(null, now)).toEqual([makeId(1)]);
  });

  it("never puts an email into a storage key", () => {
    const email = "seller@example.com";
    expect(recentlyViewedStorageKey(email)).toBe(recentlyViewedStorageKey(null));
    recordRecentlyViewedListing(makeId(1), email, Date.UTC(2026, 9, 21));
    expect(localStorage.key(0)).toBe(recentlyViewedStorageKey(null));
    expect(localStorage.key(0)).not.toContain(email);
  });

  it("clears malformed JSON and returns an empty history", () => {
    const key = recentlyViewedStorageKey(null);
    localStorage.setItem(key, "{not valid json");

    expect(readRecentlyViewedListingIds(null)).toEqual([]);
    expect(localStorage.getItem(key)).toBeNull();
  });

  it("returns an empty history when localStorage reads are blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage blocked");
    });

    expect(readRecentlyViewedListingIds(null)).toEqual([]);
  });

  it("treats unavailable localStorage as an empty, non-blocking state", () => {
    vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
      throw new Error("storage disabled");
    });

    expect(readRecentlyViewedListingIds(null)).toEqual([]);
    expect(recordRecentlyViewedListing(makeId(1), null)).toEqual([]);
    expect(() => removeRecentlyViewedListing(null, makeId(1))).not.toThrow();
    expect(() => clearRecentlyViewedListings(null)).not.toThrow();
  });

  it("keeps the caller working when localStorage writes or clears are blocked", () => {
    const now = Date.UTC(2026, 9, 21);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage blocked");
    });
    expect(recordRecentlyViewedListing(makeId(1), null, now)).toEqual([]);

    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("storage blocked");
    });
    expect(() => clearRecentlyViewedListings(null)).not.toThrow();
  });
});
