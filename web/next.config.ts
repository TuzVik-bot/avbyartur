import type { NextConfig } from "next";

// Headers in next.config are evaluated at build time, so the web image must
// be built with AVTORINOK_PUBLIC_INDEXING_ENABLED matching the deployment
// mode. Mismatch fails closed: the noindex header stays and the site remains
// unindexed until the image is rebuilt in the public mode.
const publicIndexing = process.env.AVTORINOK_PUBLIC_INDEXING_ENABLED === "true";

const nextConfig: NextConfig = {
  output: "standalone",
  // Resolve metadata before sending HTML for every browser and crawler.
  // Streaming metadata otherwise appends title/canonical/robots to the body.
  htmlLimitedBots: /.*/,
  poweredByHeader: false,
  images: {
    formats: ["image/avif", "image/webp"],
    // Listing photos are immutable once uploaded; let the optimizer cache
    // transforms for a day even if an upstream response lacks cache headers.
    minimumCacheTTL: 86_400,
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          // The closed pilot blocks indexing at the HTTP layer; the public
          // mode relies on per-page metadata instead.
          ...(publicIndexing ? [] : [{ key: "X-Robots-Tag", value: "noindex, nofollow, noarchive" }]),
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          ...(publicIndexing ? [{ key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" }] : []),
        ],
      },
    ];
  }
};

export default nextConfig;
