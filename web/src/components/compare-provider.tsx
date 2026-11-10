"use client";

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { addComparisonId, removeComparisonId, clearComparisonIds, useComparisonIds, LEGACY_COMPARISON_STORAGE_KEY, MAX_COMPARISON_ITEMS } from "@/lib/comparison-state";

export const COMPARE_STORAGE_KEY = LEGACY_COMPARISON_STORAGE_KEY;
export const MAX_COMPARE_LISTINGS = MAX_COMPARISON_ITEMS;
export function parseCompareIds(value: string | null): string[] {
  try {
    const parsed: unknown = JSON.parse(value || "[]");
    return Array.isArray(parsed) ? [...new Set(parsed.filter((id): id is string => typeof id === "string" && id.length > 0))].slice(0, MAX_COMPARE_LISTINGS) : [];
  } catch { return []; }
}
type CompareContextValue = { ids: string[]; hydrated: boolean; storageAvailable: boolean; add: (id: string) => boolean; remove: (id: string) => void; clear: () => void };
const CompareContext = createContext<CompareContextValue | null>(null);
export function CompareProvider({ children }: { children: ReactNode }) {
  const ids = useComparisonIds();
  const [hydrated, setHydrated] = useState(false);
  const [storageAvailable, setStorageAvailable] = useState(true);
  useEffect(() => { try { window.localStorage.getItem(COMPARE_STORAGE_KEY); } catch { setStorageAvailable(false); } setHydrated(true); }, []);
  const value = useMemo(() => ({ ids, hydrated, storageAvailable, add: addComparisonId, remove: (id: string) => { removeComparisonId(id); }, clear: clearComparisonIds }), [ids, hydrated, storageAvailable]);
  return <CompareContext.Provider value={value}>{children}</CompareContext.Provider>;
}
export function useCompare() {
  const value = useContext(CompareContext);
  if (!value) throw new Error("useCompare must be used inside CompareProvider");
  return value;
}
