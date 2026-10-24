import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SITE_ORIGIN } from "@/lib/site-config";
import robots from "@/app/robots";

const mocks = vi.hoisted(() => ({ connection: vi.fn() }));

vi.mock("next/server", () => ({ connection: mocks.connection }));

beforeEach(() => {
  vi.stubEnv("AVTORINOK_PUBLIC_INDEXING_ENABLED", undefined);
  mocks.connection.mockReset();
});

afterEach(() => vi.unstubAllEnvs());

describe("closed pilot robots policy", () => {
  it("preserves page crawling for noindex directives and omits sitemap discovery", async () => {
    expect(await robots()).toEqual({ rules: { userAgent: "*", disallow: "/api/v1/" } });
    expect(mocks.connection).toHaveBeenCalledTimes(1);
  });

  it("preserves the current crawler policy when the exact opt-in is enabled", async () => {
    vi.stubEnv("AVTORINOK_PUBLIC_INDEXING_ENABLED", "true");

    expect(await robots()).toEqual({
      rules: { userAgent: "*", disallow: "/api/v1/" },
      sitemap: `${SITE_ORIGIN}/sitemap.xml`,
    });
  });
});
