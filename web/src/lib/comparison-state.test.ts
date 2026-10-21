import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { addComparisonId, clearComparisonIds, getComparisonIds, MAX_COMPARISON_ITEMS, removeComparisonId, COMPARISON_STORAGE_KEY } from "@/lib/comparison-state";

describe("comparison selection storage", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => localStorage.clear());

  it("keeps unique listing IDs and enforces the four item limit", () => {
    expect(addComparisonId("one")).toBe(true);
    expect(addComparisonId("one")).toBe(true);
    expect(addComparisonId("two")).toBe(true);
    expect(addComparisonId("three")).toBe(true);
    expect(addComparisonId("four")).toBe(true);
    expect(addComparisonId("five")).toBe(false);
    expect(getComparisonIds()).toEqual(["one", "two", "three", "four"]);
    expect(getComparisonIds()).toHaveLength(MAX_COMPARISON_ITEMS);
  });

  it("ignores malformed, empty, duplicated, and non-string stored values", () => {
    localStorage.setItem(COMPARISON_STORAGE_KEY, JSON.stringify(["one", "", "one", 7, "two"]));
    expect(getComparisonIds()).toEqual(["one", "two"]);

    localStorage.setItem(COMPARISON_STORAGE_KEY, "not json");
    expect(getComparisonIds()).toEqual([]);
  });

  it("removes one listing and clears the remaining selection", () => {
    addComparisonId("one");
    addComparisonId("two");
    expect(removeComparisonId("one")).toBe(true);
    expect(removeComparisonId("missing")).toBe(false);
    expect(getComparisonIds()).toEqual(["two"]);

    clearComparisonIds();
    expect(getComparisonIds()).toEqual([]);
  });

  it("keeps the selection usable when browser storage throws", () => {
    const originalGet = Storage.prototype.getItem;
    const originalSet = Storage.prototype.setItem;
    Storage.prototype.getItem = () => { throw new Error("blocked"); };
    Storage.prototype.setItem = () => { throw new Error("blocked"); };
    try {
      expect(addComparisonId("one")).toBe(true);
      expect(getComparisonIds()).toEqual(["one"]);
    } finally {
      Storage.prototype.getItem = originalGet;
      Storage.prototype.setItem = originalSet;
    }
  });
});
