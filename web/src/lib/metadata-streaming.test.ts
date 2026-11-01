import { describe, expect, it } from "vitest";
import { shouldServeStreamingMetadata } from "next/dist/server/lib/streaming-metadata";
import nextConfig from "../../next.config";

describe("SEO metadata delivery", () => {
  it.each([
    "Mozilla/5.0 Chrome/131.0.0.0 Safari/537.36",
    "Screaming Frog SEO Spider/22.0",
    "Googlebot/2.1 (+http://www.google.com/bot.html)",
    "bingbot/2.0",
    "curl/8.7.1",
    "CustomCrawler/1.0",
  ])("waits for head metadata for %s", (userAgent) => {
    expect(shouldServeStreamingMetadata(userAgent, nextConfig.htmlLimitedBots?.source)).toBe(false);
  });
});
