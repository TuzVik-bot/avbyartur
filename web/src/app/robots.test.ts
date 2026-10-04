import { describe, expect, it } from "vitest";
import robots from "@/app/robots";

describe("closed pilot robots policy", () => {
  it("does not hide page-level noindex directives from crawlers", () => {
    expect(robots()).toEqual({
      rules: { userAgent: "*", disallow: "/api/v1/" },
      sitemap: "https://suite-s1.denjik.by/sitemap.xml",
    });
  });
});
