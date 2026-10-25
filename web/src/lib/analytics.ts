/** First-party funnel events. Until the product provides an approved consent control,
 * callers must pass consent="granted"; no analytics request is sent by default.
 */
export type ContactChannel = "phone" | "telegram" | "viber" | "internal_chat";
export type AnalyticsConsent = "granted" | "denied" | "unknown";

const CONTACT_CHANNELS: ReadonlySet<string> = new Set(["phone", "telegram", "viber", "internal_chat"]);

export async function trackContactClick(input: {
  listingId: string;
  channel: ContactChannel;
  consent: AnalyticsConsent;
}): Promise<boolean> {
  if (input.consent !== "granted" || !input.listingId || !CONTACT_CHANNELS.has(input.channel)) return false;
  try {
    const response = await fetch("/api/v1/analytics/events", {
      method: "POST",
      headers: { "content-type": "application/json", "X-Analytics-Consent": "granted" },
      body: JSON.stringify({
        listing_id: input.listingId,
        channel: input.channel,
        occurred_at: new Date().toISOString(),
        dedup_id: crypto.randomUUID(),
      }),
      keepalive: true,
    });
    return response.ok;
  } catch {
    // Measurement must never block a call, message, or navigation.
    return false;
  }
}

export type FrontendErrorType = "Error" | "TypeError" | "RangeError" | "ReferenceError" | "SyntaxError" | "NetworkError" | "ApiClientError" | "ChunkLoadError";
export type SafeBreadcrumb = "listing_detail_loaded" | "contact_click" | "contact_reveal_success" | "internal_chat_opened" | "api_request_failed";
const ERROR_TYPES: ReadonlySet<string> = new Set(["Error", "TypeError", "RangeError", "ReferenceError", "SyntaxError", "NetworkError", "ApiClientError", "ChunkLoadError"]);
const SAFE_BREADCRUMBS: ReadonlySet<string> = new Set(["listing_detail_loaded", "contact_click", "contact_reveal_success", "internal_chat_opened", "api_request_failed"]);
const SAFE_RELEASE = /^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$/;

/** Send scrubbed operational metadata only; errors, stacks, URLs and arbitrary text are never sent. */
export async function reportFrontendError(input: {
  errorType: FrontendErrorType;
  releaseId: string;
  breadcrumbs: readonly SafeBreadcrumb[];
}): Promise<boolean> {
  if (!ERROR_TYPES.has(input.errorType) || !SAFE_RELEASE.test(input.releaseId)) return false;
  const breadcrumbs = input.breadcrumbs.filter((value) => SAFE_BREADCRUMBS.has(value)).slice(-10);
  try {
    const response = await fetch("/api/v1/analytics/errors", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ error_type: input.errorType, release_id: input.releaseId, breadcrumbs }),
      keepalive: true,
    });
    return response.ok;
  } catch {
    return false;
  }
}
