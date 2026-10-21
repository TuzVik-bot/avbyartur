export const MAX_RECENT_LISTINGS = 12;
export const RECENT_LISTINGS_TTL_MS = 30 * 24 * 60 * 60 * 1000;
const MAX_FUTURE_SKEW_MS = 5 * 60 * 1000;
const STORAGE_PREFIX = "avtorinok:recent-listings:v1:";
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

type RecentEntry = { id: string; viewedAt: number };

function isOpaqueUserId(userId: string | null): userId is string {
  return typeof userId === "string" && UUID_PATTERN.test(userId);
}

export function recentlyViewedStorageKey(userId: string | null) {
  // Account IDs from the API are UUIDs. Treat anything else as guest input so
  // an accidental email, phone number, or display name is never persisted.
  return `${STORAGE_PREFIX}${isOpaqueUserId(userId) ? `account:${userId.toLowerCase()}` : "guest"}`;
}

function browserStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function readEntries(userId: string | null, now: number): RecentEntry[] {
  const storage = browserStorage();
  if (!storage) return [];
  const key = recentlyViewedStorageKey(userId);
  let raw: string | null;
  try {
    raw = storage.getItem(key);
  } catch {
    return [];
  }
  if (raw === null) return [];

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    removeStoredHistory(storage, key);
    return [];
  }
  if (!Array.isArray(parsed)) {
    removeStoredHistory(storage, key);
    return [];
  }

  const safeNow = Number.isFinite(now) && now > 0 ? now : Date.now();
  const latestById = new Map<string, RecentEntry>();
  for (const item of parsed) {
    if (
      !item || typeof item !== "object" ||
      typeof item.id !== "string" || !UUID_PATTERN.test(item.id) ||
      typeof item.viewedAt !== "number" || !Number.isFinite(item.viewedAt) ||
      item.viewedAt > safeNow + MAX_FUTURE_SKEW_MS || safeNow - item.viewedAt >= RECENT_LISTINGS_TTL_MS
    ) continue;
    const id = item.id.toLowerCase();
    const existing = latestById.get(id);
    if (!existing || item.viewedAt > existing.viewedAt) {
      latestById.set(id, { id, viewedAt: item.viewedAt });
    }
  }

  const entries = [...latestById.values()]
    .sort((left, right) => right.viewedAt - left.viewedAt)
    .slice(0, MAX_RECENT_LISTINGS);
  const normalized = JSON.stringify(entries);
  if (normalized !== raw) {
    try {
      storage.setItem(key, normalized);
    } catch {
      // Sanitizing old values is best effort when browser storage is blocked.
    }
  }
  return entries;
}

function removeStoredHistory(storage: Storage, key: string) {
  try {
    storage.removeItem(key);
  } catch {
    // Corrupt history should not make listing pages fail when storage is blocked.
  }
}

function writeEntries(userId: string | null, entries: RecentEntry[]) {
  const storage = browserStorage();
  if (!storage) return;
  try {
    storage.setItem(recentlyViewedStorageKey(userId), JSON.stringify(entries.slice(0, MAX_RECENT_LISTINGS)));
  } catch {
    // The current page remains usable if browser storage is unavailable.
  }
}

export function readRecentlyViewedListingIds(userId: string | null, now = Date.now()): string[] {
  return readEntries(userId, now).map(({ id }) => id);
}

/** Store a listing only when its public detail page was actually visited. */
export function recordRecentlyViewedListing(id: string, userId: string | null, now = Date.now()): string[] {
  const safeNow = Number.isFinite(now) && now > 0 ? now : Date.now();
  const normalizedId = id.toLowerCase();
  const prior = readEntries(userId, safeNow).filter((entry) => entry.id !== normalizedId);
  if (UUID_PATTERN.test(normalizedId)) {
    writeEntries(userId, [{ id: normalizedId, viewedAt: safeNow }, ...prior]);
  }
  return prior.map(({ id: priorId }) => priorId).slice(0, MAX_RECENT_LISTINGS);
}

export function removeRecentlyViewedListing(userId: string | null, id: string, now = Date.now()) {
  writeEntries(userId, readEntries(userId, now).filter((entry) => entry.id !== id));
}

export function clearRecentlyViewedListings(userId: string | null) {
  const storage = browserStorage();
  if (!storage) return;
  try {
    storage.removeItem(recentlyViewedStorageKey(userId));
  } catch {
    // Clearing is best effort when browser storage is unavailable.
  }
}
