import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Content-Type-Options", value: "nosniff" }
        ]
      },
      ...["/account/:path*", "/admin/:path*", "/moderation/:path*", "/api/:path*", "/login", "/register", "/recover", "/verify-email", "/sell"].map((source) => ({
        source,
        headers: [{ key: "X-Robots-Tag", value: "noindex, nofollow, noarchive" }]
      }))
    ];
  }
};

export default nextConfig;
