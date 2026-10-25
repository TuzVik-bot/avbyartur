import { assertSafeLocalPath, DEFAULT_LOCALE, isSupportedLocale, localizedPath, type Locale } from "./i18n";

export const DEFAULT_SITE_NAME = "Авторынок BY";
export const DEFAULT_SITE_ORIGIN = "https://suite-s1.denjik.by";

export type SiteEnvironment = Record<string, string | undefined>;

export function getSiteConfig(environment: SiteEnvironment = process.env) {
  const siteName = environment.SITE_NAME?.trim() || DEFAULT_SITE_NAME;
  const configuredOrigin = environment.SITE_ORIGIN?.trim() || DEFAULT_SITE_ORIGIN;
  const url = new URL(configuredOrigin);

  if (
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.pathname !== "/" ||
    url.search ||
    url.hash
  ) {
    throw new Error("SITE_ORIGIN must be an HTTP(S) origin without credentials, path, query, or fragment");
  }

  return { siteName, siteOrigin: url.origin };
}

const siteConfig = getSiteConfig();

export const SITE_NAME = siteConfig.siteName;
export const SITE_ORIGIN = siteConfig.siteOrigin;

export function siteUrl(pathname: string, locale?: string): string {
  if (!pathname.startsWith("/") || pathname.startsWith("//") || pathname.includes("?") || pathname.includes("#")) {
    throw new Error("Site URLs must be absolute local paths without query or fragment");
  }
  assertSafeLocalPath(pathname);

  const canonicalPath = locale === undefined ? pathname : localizedPath(pathname, locale);
  return new URL(canonicalPath, `${SITE_ORIGIN}/`).toString();
}

export function localeMetadata(pathname: string, locale: string = DEFAULT_LOCALE): {
  canonical: string;
  languages: Record<Locale, string>;
} {
  if (!isSupportedLocale(locale)) throw new Error(`Unsupported locale: ${locale}`);
  const canonical = siteUrl(pathname, locale);
  return { canonical, languages: { [locale]: canonical } as Record<Locale, string> };
}
