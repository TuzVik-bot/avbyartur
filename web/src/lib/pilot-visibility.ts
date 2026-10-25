import type { Metadata } from "next";

const PUBLIC_INDEXING_ENV = "AVTORINOK_PUBLIC_INDEXING_ENABLED";

// Exact "true" switches the whole site into public indexing mode: sitemap
// discovery, indexable root metadata and no global X-Robots-Tag header.
// The web image must be built with the same value (next.config headers are
// evaluated at build time), while this runtime check keeps metadata, robots
// and sitemap consistent with the deployed mode.
export function isPublicIndexingEnabled(): boolean {
  return process.env[PUBLIC_INDEXING_ENV] === "true";
}

const closedRobots: NonNullable<Metadata["robots"]> = {
  index: false,
  follow: false,
  noarchive: true,
  googleBot: { index: false, follow: false, noimageindex: true },
};

const openRobots: NonNullable<Metadata["robots"]> = { index: true, follow: true };

// Root robots policy. Per-page overrides (sold listings, thin category
// landings, account/admin areas) still apply on top in the public mode.
export function rootRobots(): NonNullable<Metadata["robots"]> {
  return isPublicIndexingEnabled() ? openRobots : closedRobots;
}
