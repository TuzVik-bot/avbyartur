const PUBLIC_INDEXING_ENV = "AVTORINOK_PUBLIC_INDEXING_ENABLED";

// Only exact "true" exposes sitemap discovery; root metadata and X-Robots-Tag remain noindex.
export function isPublicIndexingEnabled(): boolean {
  return process.env[PUBLIC_INDEXING_ENV] === "true";
}
