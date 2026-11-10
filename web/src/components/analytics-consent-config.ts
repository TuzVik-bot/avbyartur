export const DEFAULT_GA_MEASUREMENT_ID = "G-48P5WKB0Z5";

const GA4_MEASUREMENT_ID = /^G-[A-Z0-9]{4,20}$/;

// Private sections may carry personal data or one-time tokens in their URLs.
const PRIVATE_PATH_PREFIXES = ["/admin", "/account", "/moderation", "/recover", "/verify-email", "/login"];

/** Read the GA4 ID from server env; keep the production ID when unset or malformed. */
export function resolveAnalyticsMeasurementId(environment: Record<string, string | undefined> = process.env): string {
  const configured = environment.GA_MEASUREMENT_ID?.trim();
  return configured && GA4_MEASUREMENT_ID.test(configured) ? configured : DEFAULT_GA_MEASUREMENT_ID;
}

/** Match whole path segments so "/login-help" stays measurable while "/login/x" does not. */
export function isAnalyticsExcludedPath(pathname: string): boolean {
  return PRIVATE_PATH_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}
