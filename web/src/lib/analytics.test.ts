import { afterEach, describe, expect, it, vi } from "vitest";
import { trackContactClick } from "./analytics";
import { setMeasurementConsent, setMeasurementEnabled } from "./funnel-analytics";

afterEach(() => vi.unstubAllGlobals());

describe("contact click analytics", () => {
  it("does not send without explicit analytics consent", async () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    await expect(trackContactClick({ listingId: "listing-1", channel: "phone", consent: "unknown" })).resolves.toBe(false);
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("sends an allowlisted payload after consent and fails open", async () => {
    const gtag = vi.fn();
    vi.stubGlobal("gtag", gtag);
    setMeasurementEnabled(true);
    setMeasurementConsent(true);
    try {
      await expect(trackContactClick({ listingId: "listing-1", channel: "telegram", consent: "granted" })).resolves.toBe(true);
      expect(gtag).toHaveBeenCalledTimes(1);
      const [command, eventName, payload] = gtag.mock.calls[0] as [string, string, Record<string, unknown>];
      expect(command).toBe("event");
      expect(eventName).toBe("contact_channel_clicked");
      expect(Object.keys(payload).sort()).toEqual(["channel", "page_location", "page_referrer", "page_title"]);
      expect(payload.channel).toBe("telegram");
      expect(JSON.stringify(payload)).not.toMatch(/listing-1|phone|vin|email|message/i);

      gtag.mockImplementation(() => { throw new Error("blocked"); });
      await expect(trackContactClick({ listingId: "listing-1", channel: "viber", consent: "granted" })).resolves.toBe(false);
    } finally {
      setMeasurementConsent(false);
      setMeasurementEnabled(false);
    }
  });
  it("accepts only known contact channels", async () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    await expect(trackContactClick({ listingId: "listing-1", channel: "email" as never, consent: "granted" })).resolves.toBe(false);
    expect(fetcher).not.toHaveBeenCalled();
  });
});

describe("frontend error reports", () => {
  it("sends only error type, release, and allowlisted breadcrumbs", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(null, { status: 202 }));
    vi.stubGlobal("fetch", fetcher);
    const { reportFrontendError } = await import("./analytics");
    await expect(reportFrontendError({ errorType: "TypeError", releaseId: "abc123", breadcrumbs: ["contact_click"] })).resolves.toBe(true);
    expect(fetcher).toHaveBeenCalledWith("/api/v1/analytics/errors", expect.objectContaining({ method: "POST" }));
    const body = JSON.parse(String(fetcher.mock.calls[0][1].body));
    expect(body).toEqual({ error_type: "TypeError", release_id: "abc123", breadcrumbs: ["contact_click"] });
    expect(JSON.stringify(body)).not.toMatch(/url|stack|message|private/i);
  });

  it("fails closed for unapproved release IDs and fails open on transport errors", async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error("network failure"));
    vi.stubGlobal("fetch", fetcher);
    const { reportFrontendError } = await import("./analytics");
    await expect(reportFrontendError({ errorType: "TypeError", releaseId: "https://secret.example", breadcrumbs: [] })).resolves.toBe(false);
    expect(fetcher).not.toHaveBeenCalled();
    await expect(reportFrontendError({ errorType: "TypeError", releaseId: "abc123", breadcrumbs: ["https://private.example"] as never })).resolves.toBe(false);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
