export type FunnelEventPayloads = {
  search_submitted: { has_filters?: boolean };
  search_results_viewed: { result_count?: number };
  listing_opened: { source?: "search" | "favorites" | "other" };
  contact_reveal_succeeded: { channel?: "phone" | "telegram" | "viber" | "internal_chat" };
  contact_channel_clicked: { channel: "phone" | "telegram" | "viber" | "internal_chat" };
  registration_completed: { method?: "email" | "other" };
  listing_draft_saved: { has_photos?: boolean };
  listing_submission_succeeded: { has_photos?: boolean };
};

type EventName = keyof FunnelEventPayloads;
type Gtag = (...args: unknown[]) => void;
declare global { interface Window { gtag?: Gtag; dataLayer?: unknown[] } }
let enabled = false;
let consentGranted = false;
const readinessListeners = new Set<() => void>();
export function measurementReady() { return enabled && consentGranted; }
export function subscribeMeasurementReady(listener: () => void) {
  readinessListeners.add(listener);
  return () => { readinessListeners.delete(listener); };
}
function updateReadiness(update: () => void) {
  const previous = measurementReady();
  update();
  if (previous !== measurementReady()) readinessListeners.forEach((listener) => listener());
}
export function setMeasurementConsent(value: boolean) { updateReadiness(() => { consentGranted = value; }); }
export function setMeasurementEnabled(value: boolean) { updateReadiness(() => { enabled = value; }); }

const rules: Record<EventName, Record<string, (value: unknown) => boolean>> = {
  search_submitted: { has_filters: (v) => typeof v === "boolean" },
  search_results_viewed: { result_count: (v) => typeof v === "number" && Number.isInteger(v) && v >= 0 && v <= 100000 },
  listing_opened: { source: (v) => ["search", "favorites", "other"].includes(v as string) },
  contact_reveal_succeeded: { channel: (v) => ["phone", "telegram", "viber", "internal_chat"].includes(v as string) },
  contact_channel_clicked: { channel: (v) => ["phone", "telegram", "viber", "internal_chat"].includes(v as string) },
  registration_completed: { method: (v) => ["email", "other"].includes(v as string) },
  listing_draft_saved: { has_photos: (v) => typeof v === "boolean" },
  listing_submission_succeeded: { has_photos: (v) => typeof v === "boolean" },
};

export function trackFunnelEvent<E extends EventName>(name: E, payload: FunnelEventPayloads[E]): boolean {
  if (!consentGranted || !enabled || typeof window === "undefined" || typeof window.gtag !== "function" || !Object.hasOwn(rules, name)) return false;
  try {
    const safe: Record<string, unknown> = { page_location: window.location.origin, page_title: "Avtorinok", page_referrer: "" };
    const values = payload && typeof payload === "object" ? payload as Record<string, unknown> : {};
    for (const [key, validate] of Object.entries(rules[name])) if (validate(values[key])) safe[key] = values[key];
    if (name === "contact_channel_clicked" && !safe.channel) return false;
    window.gtag("event", name, safe);
    return true;
  } catch { return false; }
}
