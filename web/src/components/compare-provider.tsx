"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export const COMPARE_STORAGE_KEY = "avtorinok.compare.v1";
export const MAX_COMPARE_LISTINGS = 4;

export function parseCompareIds(value: string | null): string[] {
  if (!value) return [];
  try {
    const parsed: unknown = JSON.parse(value);
    if (!Array.isArray(parsed)) return [];
    return [...new Set(parsed.filter((id): id is string => typeof id === "string" && id.length > 0))].slice(0, MAX_COMPARE_LISTINGS);
  } catch {
    return [];
  }
}

type CompareContextValue = {
  ids: string[];
  hydrated: boolean;
  storageAvailable: boolean;
  add: (id: string) => boolean;
  remove: (id: string) => void;
  clear: () => void;
};

const CompareContext = createContext<CompareContextValue | null>(null);

export function CompareProvider({ children }: { children: ReactNode }) {
  const [ids, setIds] = useState<string[]>([]);
  const [hydrated, setHydrated] = useState(false);
  const [storageAvailable, setStorageAvailable] = useState(true);

  useEffect(() => {
    try {
      setIds(parseCompareIds(window.localStorage.getItem(COMPARE_STORAGE_KEY)));
    } catch {
      setStorageAvailable(false);
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    try {
      window.localStorage.setItem(COMPARE_STORAGE_KEY, JSON.stringify(ids));
      setStorageAvailable(true);
    } catch {
      setStorageAvailable(false);
    }
  }, [hydrated, ids]);

  useEffect(() => {
    function syncStorage(event: StorageEvent) {
      if (event.key !== null && event.key !== COMPARE_STORAGE_KEY) return;
      setIds(parseCompareIds(event.key === null ? null : event.newValue));
    }
    window.addEventListener("storage", syncStorage);
    return () => window.removeEventListener("storage", syncStorage);
  }, []);

  const add = useCallback((id: string) => {
    let accepted = true;
    setIds((current) => {
      if (current.includes(id)) return current;
      if (current.length >= MAX_COMPARE_LISTINGS) {
        accepted = false;
        return current;
      }
      return [...current, id];
    });
    return accepted;
  }, []);
  const remove = useCallback((id: string) => setIds((current) => current.filter((value) => value !== id)), []);
  const clear = useCallback(() => setIds([]), []);

  const value = useMemo(() => ({ ids, hydrated, storageAvailable, add, remove, clear }), [ids, hydrated, storageAvailable, add, remove, clear]);
  return <CompareContext.Provider value={value}>{children}</CompareContext.Provider>;
}

export function useCompare() {
  const value = useContext(CompareContext);
  if (!value) throw new Error("useCompare must be used inside CompareProvider");
  return value;
}
