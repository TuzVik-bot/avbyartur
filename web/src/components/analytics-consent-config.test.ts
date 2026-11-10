import { describe, expect, it } from "vitest";
import { DEFAULT_GA_MEASUREMENT_ID, isAnalyticsExcludedPath, resolveAnalyticsMeasurementId } from "./analytics-consent-config";

describe("analytics measurement ID", () => {
  it("falls back to the production ID when the variable is unset or blank", () => {
    expect(DEFAULT_GA_MEASUREMENT_ID).toBe("G-48P5WKB0Z5");
    expect(resolveAnalyticsMeasurementId({})).toBe(DEFAULT_GA_MEASUREMENT_ID);
    expect(resolveAnalyticsMeasurementId({ GA_MEASUREMENT_ID: "  " })).toBe(DEFAULT_GA_MEASUREMENT_ID);
  });

  it("uses a valid configured GA4 ID", () => {
    expect(resolveAnalyticsMeasurementId({ GA_MEASUREMENT_ID: " G-ABC123XYZ " })).toBe("G-ABC123XYZ");
  });

  it("rejects malformed IDs instead of injecting them into a script URL", () => {
    expect(resolveAnalyticsMeasurementId({ GA_MEASUREMENT_ID: "G-1\"><script>" })).toBe(DEFAULT_GA_MEASUREMENT_ID);
    expect(resolveAnalyticsMeasurementId({ GA_MEASUREMENT_ID: "UA-1234-1" })).toBe(DEFAULT_GA_MEASUREMENT_ID);
  });
});

describe("analytics private paths", () => {
  it.each(["/admin", "/admin/monitoring", "/account", "/account/listings", "/moderation", "/recover", "/verify-email", "/login"])("excludes %s", (pathname) => {
    expect(isAnalyticsExcludedPath(pathname)).toBe(true);
  });

  it.each(["/", "/cars", "/cars/bmw", "/sell", "/administrators-guide", "/login-help"])("keeps public path %s measurable", (pathname) => {
    expect(isAnalyticsExcludedPath(pathname)).toBe(false);
  });
});
