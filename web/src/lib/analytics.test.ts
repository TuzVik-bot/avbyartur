import { afterEach, describe, expect, it, vi } from "vitest";
import { trackContactClick } from "./analytics";

afterEach(() => vi.unstubAllGlobals());

describe("contact click analytics", () => {
  it("does not send without explicit analytics consent", async () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    await expect(trackContactClick({ listingId: "listing-1", channel: "phone", consent: "unknown" })).resolves.toBe(false);
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("sends an allowlisted payload after consent and fails open", async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error("offline"));
    vi.stubGlobal("fetch", fetcher);
    await expect(trackContactClick({ listingId: "listing-1", channel: "telegram", consent: "granted" })).resolves.toBe(false);
    const [url, request] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/analytics/events");
    expect(new Headers(request.headers).get("X-Analytics-Consent")).toBe("granted");
    const payload = JSON.parse(String(request.body));
    expect(Object.keys(payload).sort()).toEqual(["channel", "dedup_id", "listing_id", "occurred_at"]);
    expect(payload).toMatchObject({ listing_id: "listing-1", channel: "telegram" });
    expect(payload.dedup_id).toMatch(/^[0-9a-f-]{36}$/i);
    expect(payload.occurred_at).toMatch(/^\d{4}-/);
    expect(JSON.stringify(payload)).not.toMatch(/phone|vin|email|message|url/i);
  });
  it("accepts only known contact channels", async () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    await expect(trackContactClick({ listingId: "listing-1", channel: "email" as never, consent: "granted" })).resolves.toBe(false);
    expect(fetcher).not.toHaveBeenCalled();
  });
});
