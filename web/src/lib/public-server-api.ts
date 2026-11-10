import { ApiClientError, internalApiBase } from "@/lib/api";
import type { ApiErrorShape } from "@/lib/types";

export const SERVER_API_TIMEOUT_MS = 5000;
export const PUBLIC_REFERENCE_TTL_MS = 5 * 60 * 1000;
// Catalog lookups carry slugs from the URL, so the key space is visitor-controlled and must stay bounded.
export const MAX_PUBLIC_REFERENCE_CACHE_ENTRIES = 500;

export function serverApiUrl(path: string) {
  return `${internalApiBase()}/${path.replace(/^\//, "")}`;
}

export async function parseServerApiResponse<T>(response: Response): Promise<T> {
  const payload: unknown = await response.json().catch(() => undefined);
  if (!response.ok) throw new ApiClientError(response.status, (payload || {}) as Partial<ApiErrorShape>);
  return payload as T;
}

type CacheEntry = { expiresAt: number; value: Promise<unknown> };

// The root layout forces dynamic rendering, which makes Next ignore per-fetch
// `revalidate` (fetchCache = "force-no-store"). Reference data is identical for
// every visitor, so it is memoized in-process instead and fetched without cookies.
const referenceCache = new Map<string, CacheEntry>();

export function clearPublicReferenceCache() {
  referenceCache.clear();
}

export function publicReferenceCacheSize() {
  return referenceCache.size;
}

function makeRoomForEntry(now: number) {
  if (referenceCache.size < MAX_PUBLIC_REFERENCE_CACHE_ENTRIES) return;
  for (const [key, entry] of referenceCache) {
    if (entry.expiresAt <= now) referenceCache.delete(key);
  }
  // Map keeps insertion order, so the first keys are the oldest entries.
  for (const key of referenceCache.keys()) {
    if (referenceCache.size < MAX_PUBLIC_REFERENCE_CACHE_ENTRIES) break;
    referenceCache.delete(key);
  }
}

export async function publicServerApiRequest<T>(path: string): Promise<T> {
  const now = Date.now();
  const cached = referenceCache.get(path);
  if (cached && cached.expiresAt > now) return cached.value as Promise<T>;
  referenceCache.delete(path);
  const value = fetch(serverApiUrl(path), {
    cache: "no-store",
    signal: AbortSignal.timeout(SERVER_API_TIMEOUT_MS)
  }).then((response) => parseServerApiResponse<T>(response));
  makeRoomForEntry(now);
  referenceCache.set(path, { expiresAt: now + PUBLIC_REFERENCE_TTL_MS, value });
  // Failures must not be served from the cache.
  value.catch(() => {
    if (referenceCache.get(path)?.value === value) referenceCache.delete(path);
  });
  return value;
}
