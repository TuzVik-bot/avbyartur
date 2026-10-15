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
