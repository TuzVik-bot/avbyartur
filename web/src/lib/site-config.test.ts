import { describe, expect, it } from "vitest";
import { DEFAULT_SITE_NAME, getSiteConfig, localeMetadata, SITE_ORIGIN, siteUrl } from "./site-config";

describe("site configuration", () => {
  it("uses the configured brand and a normalized trusted origin", () => {
    expect(getSiteConfig({ SITE_NAME: "  Marketplace BY ", SITE_ORIGIN: "https://EXAMPLE.com/" })).toEqual({
      siteName: "Marketplace BY",
      siteOrigin: "https://example.com"
    });
  });

  it("uses stable defaults when configuration is absent", () => {
    expect(getSiteConfig({})).toEqual({ siteName: DEFAULT_SITE_NAME, siteOrigin: "https://suite-s1.denjik.by" });
  });

  it.each([
    "https://user:secret@example.com",
    "https://example.com/subpath",
    "https://example.com?preview=true",
    "ftp://example.com"
  ])("rejects an unsafe SITE_ORIGIN: %s", (SITE_ORIGIN) => {
    expect(() => getSiteConfig({ SITE_ORIGIN })).toThrow(/SITE_ORIGIN/);
  });

  it("builds canonical URLs from the configured origin and local paths only", () => {
    expect(siteUrl("/cars/bmw")).toBe(`${SITE_ORIGIN}/cars/bmw`);
    expect(() => siteUrl("//attacker.example/path")).toThrow();
    expect(() => siteUrl("https://attacker.example/path")).toThrow();
  });

  it("builds the canonical URL for an explicit Russian locale alias", () => {
    expect(siteUrl("/ru/cars/bmw", "ru")).toBe(`${SITE_ORIGIN}/cars/bmw`);
  });

  it("builds locale-aware metadata without changing the current Russian canonical", () => {
    expect(localeMetadata("/", "ru")).toEqual({
      canonical: `${SITE_ORIGIN}/`,
      languages: { ru: `${SITE_ORIGIN}/` }
    });
  });

  it("rejects unsupported locale and unsafe locale-prefixed aliases", () => {
    expect(() => siteUrl("/cars", "en")).toThrow(/Unsupported locale/);
    expect(() => siteUrl("/ru//cars", "ru")).toThrow();
    expect(() => siteUrl("/ru/cars\\other", "ru")).toThrow();
    expect(() => siteUrl("/cars%2fother")).toThrow();
    expect(() => siteUrl("/cars/%2e%2e/admin")).toThrow();
  });
});
