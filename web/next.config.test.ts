import { describe, expect, it } from "vitest";
import nextConfig from "./next.config";

async function globalHeaders() {
  const rules = (await nextConfig.headers?.()) ?? [];
  const rule = rules.find((entry) => entry.source === "/:path*");
  return new Map((rule?.headers ?? []).map((header) => [header.key, header.value]));
}

describe("global security headers", () => {
  it("sends a conservative CSP without restricting scripts", async () => {
    const headers = await globalHeaders();
    const csp = headers.get("Content-Security-Policy");
    expect(csp).toBe("frame-ancestors 'none'; object-src 'none'; base-uri 'self'; form-action 'self'");
    expect(csp).not.toContain("script-src");
  });

  it("allows the microphone only for the site assistant and blocks other device APIs", async () => {
    const headers = await globalHeaders();
    expect(headers.get("Permissions-Policy")).toBe("camera=(), geolocation=(), payment=(), microphone=(self)");
  });

  it("keeps the existing baseline headers", async () => {
    const headers = await globalHeaders();
    expect(headers.get("Referrer-Policy")).toBe("strict-origin-when-cross-origin");
    expect(headers.get("X-Content-Type-Options")).toBe("nosniff");
  });
});
