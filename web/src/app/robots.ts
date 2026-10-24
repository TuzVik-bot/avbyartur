import type { MetadataRoute } from "next";
import { connection } from "next/server";
import { SITE_ORIGIN } from "@/lib/site-config";
import { isPublicIndexingEnabled } from "@/lib/pilot-visibility";

export default async function robots(): Promise<MetadataRoute.Robots> {
  await connection();
  return {
    rules: { userAgent: "*", disallow: "/api/v1/" },
    ...(isPublicIndexingEnabled() ? { sitemap: `${SITE_ORIGIN}/sitemap.xml` } : {}),
  };
}
