import { trackFunnelEvent } from "./funnel-analytics";
export type ContactChannel = "phone" | "telegram" | "viber" | "internal_chat";
export type AnalyticsConsent = "granted" | "denied" | "unknown";

const CONTACT_CHANNELS: ReadonlySet<string> = new Set(["phone", "telegram", "viber", "internal_chat"]);

export async function trackContactClick(input: {
  listingId: string;
  channel: ContactChannel;
  consent: AnalyticsConsent;
}): Promise<boolean> {
  if (input.consent !== "granted" || !CONTACT_CHANNELS.has(input.channel)) return false;
  return trackFunnelEvent("contact_channel_clicked", { channel: input.channel });
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
