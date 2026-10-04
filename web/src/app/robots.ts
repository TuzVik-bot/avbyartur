import type { MetadataRoute } from "next";
import { SITE_ORIGIN } from "@/lib/site-config";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", disallow: "/api/v1/" },
    sitemap: `${SITE_ORIGIN}/sitemap.xml`,
  };
}
