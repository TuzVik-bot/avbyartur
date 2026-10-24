"use client";

import { useMemo, useSyncExternalStore } from "react";

export const COMPARISON_STORAGE_KEY = "avtorinok:comparison";
export const MAX_COMPARISON_ITEMS = 4;

type ChangeListener = () => void;

let memoryIds: string[] = [];
const listeners = new Set<ChangeListener>();

function normalizeIds(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const ids = new Set<string>();
  for (const candidate of value) {
    if (typeof candidate !== "string" || !candidate.trim()) continue;
    ids.add(candidate);
    if (ids.size === MAX_COMPARISON_ITEMS) break;
  }
  return [...ids];
}

function readIds(): string[] {
  if (typeof window === "undefined") return [...memoryIds];
  let value: string | null;
  try {
    value = window.localStorage.getItem(COMPARISON_STORAGE_KEY);
  } catch {
    return [...memoryIds];
  }
  if (value === null) {
    memoryIds = [];
    return [];
  }
  try {
    memoryIds = normalizeIds(JSON.parse(value));
    return [...memoryIds];
  } catch {
    memoryIds = [];
    return [];
  }
}

function notifyListeners() {
  for (const listener of listeners) listener();
}

function handleStorage(event: StorageEvent) {
  if (event.key !== COMPARISON_STORAGE_KEY && event.key !== null) return;
  if (event.key === null || event.newValue === null) memoryIds = [];
  notifyListeners();
}

function writeIds(ids: string[]) {
  memoryIds = normalizeIds(ids);
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(COMPARISON_STORAGE_KEY, JSON.stringify(memoryIds));
    } catch {
      // Keep the in-memory selection usable when browser storage is blocked.
    }
  }
  notifyListeners();
}

export function subscribeToComparison(listener: ChangeListener) {
  listeners.add(listener);
  if (listeners.size === 1 && typeof window !== "undefined") {
    window.addEventListener("storage", handleStorage);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && typeof window !== "undefined") {
      window.removeEventListener("storage", handleStorage);
    }
  };
}

export function getComparisonIds(): string[] {
  return readIds();
}

export function getComparisonSnapshot(): string {
  return JSON.stringify(readIds());
}

export function useComparisonIds(): string[] {
  const snapshot = useSyncExternalStore(subscribeToComparison, getComparisonSnapshot, () => "[]");
  return useMemo(() => normalizeIds(JSON.parse(snapshot)), [snapshot]);
}

export function addComparisonId(id: string): boolean {
  if (typeof id !== "string" || !id.trim()) return false;
  const ids = readIds();
  if (ids.includes(id)) return true;
  if (ids.length >= MAX_COMPARISON_ITEMS) return false;
  writeIds([...ids, id]);
  return true;
}

export function removeComparisonId(id: string): boolean {
  const ids = readIds();
  if (!ids.includes(id)) return false;
  writeIds(ids.filter((selected) => selected !== id));
  return true;
}

export function clearComparisonIds() {
  if (readIds().length > 0) writeIds([]);
}
