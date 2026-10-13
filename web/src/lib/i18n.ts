export const SUPPORTED_LOCALES = ["ru"] as const;
export type Locale = (typeof SUPPORTED_LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "ru";

const russianMessages = {
  "layout.titleSuffix": "автомобили Беларуси",
  "layout.description": "Поиск автомобилей в Беларуси и подача объявлений в закрытом пилоте.",
  "layout.skipToMainContent": "Перейти к основному содержимому",
  "home.metadataTitle": "Автомобили Беларуси",
  "header.brandHome": "Авторынок, главная",
  "header.closeMenu": "Закрыть меню",
  "header.openMenu": "Открыть меню",
  "header.navigation": "Основная навигация",
  "header.cars": "Автомобили",
  "header.companies": "Компаниям",
  "header.usefulInformation": "Полезная информация",
  "header.customsCalculator": "Таможенный калькулятор",
  "header.currencyConverter": "Конвертер валют",
  "header.moderation": "Модерация",
  "header.administration": "Администрирование",
  "header.account": "Кабинет",
  "header.signIn": "Войти",
  "header.register": "Регистрация",
  "header.signOut": "Выйти",
  "header.sellListing": "Подать объявление",
  "header.signOutError": "Не удалось завершить сеанс. Повторите попытку."
} as const;

export const messages = { ru: russianMessages } as const;
export type MessageKey = keyof typeof russianMessages;

export function isSupportedLocale(value: unknown): value is Locale {
  return typeof value === "string" && (SUPPORTED_LOCALES as readonly string[]).includes(value);
}

export function resolveLocale(value?: string | null): Locale {
  return isSupportedLocale(value) ? value : DEFAULT_LOCALE;
}

function requireLocale(value: string): Locale {
  if (!isSupportedLocale(value)) throw new Error(`Unsupported locale: ${value}`);
  return value;
}

export function getMessage(key: MessageKey, locale?: string | null): string {
  const selected = messages[resolveLocale(locale)];
  return selected[key] ?? messages[DEFAULT_LOCALE][key];
}

export function assertSafeLocalPath(pathname: string): void {
  if (
    !pathname.startsWith("/") ||
    pathname.startsWith("//") ||
    pathname.includes("//") ||
    pathname.includes("\\") ||
    pathname.includes("?") ||
    pathname.includes("#") ||
    /%(?:2f|5c|2e)/i.test(pathname) ||
    pathname.split("/").some((segment) => segment === "." || segment === "..")
  ) {
    throw new Error("Paths must be safe absolute local paths without traversal, encoded separators, query, or fragment");
  }
}

function stripSupportedLocalePrefix(pathname: string): string {
  if (pathname === `/${DEFAULT_LOCALE}`) return "/";
  if (pathname.startsWith(`/${DEFAULT_LOCALE}/`)) return pathname.slice(DEFAULT_LOCALE.length + 1);
  return pathname;
}

/** Return the canonical route for a supported locale (the default stays unprefixed). */
export function localizedPath(pathname: string, localeValue: string = DEFAULT_LOCALE): string {
  assertSafeLocalPath(pathname);
  const locale = requireLocale(localeValue);
  const canonicalPath = stripSupportedLocalePrefix(pathname);
  if (canonicalPath.startsWith("//") || canonicalPath.includes("\\")) {
    throw new Error("Locale paths must not contain unsafe separators");
  }
  return locale === DEFAULT_LOCALE ? canonicalPath : `/${locale}${canonicalPath === "/" ? "" : canonicalPath}`;
}

export type LocaleAliasResolution =
  | { kind: "redirect"; pathname: string }
  | { kind: "pass" }
  | { kind: "none" };

function rawPathFromUrl(value: string): string {
  const scheme = /^[a-z][a-z\d+.-]*:\/\/[^/?#]*/i.exec(value);
  const start = scheme ? scheme[0].length : 0;
  const slash = scheme ? value.indexOf("/", start) : start;
  if (slash < 0) return "/";
  const remainder = value.slice(slash);
  const delimiter = remainder.search(/[?#]/);
  return delimiter < 0 ? remainder : remainder.slice(0, delimiter);
}

/** Resolve only safe, page-like /ru aliases; reserved and ambiguous paths pass through. */
export function localeAliasResolution(pathname: string, originalUrl: string = pathname): LocaleAliasResolution {
  if (pathname !== `/${DEFAULT_LOCALE}` && !pathname.startsWith(`/${DEFAULT_LOCALE}/`)) return { kind: "none" };

  const rawPath = rawPathFromUrl(originalUrl);
  if (
    rawPath.includes("\\") ||
    pathname.includes("\\") ||
    pathname.includes("//") ||
    /%(?:2f|5c|2e)/i.test(pathname) ||
    rawPath.split("/").some((segment) => segment === "." || segment === "..") ||
    pathname.split("/").some((segment) => segment === "." || segment === "..")
  ) {
    return { kind: "pass" };
  }

  const targetPathname = pathname === `/${DEFAULT_LOCALE}` ? "/" : pathname.slice(DEFAULT_LOCALE.length + 1);
  const firstSegment = targetPathname.slice(1).split("/", 1)[0]?.toLowerCase();
  const lastSegment = targetPathname.split("/").filter(Boolean).at(-1)?.toLowerCase() ?? "";
  const metadataAssetSegments = new Set(["apple-icon", "icon", "icon1", "icon2", "manifest"]);
  if (
    firstSegment === "api" ||
    firstSegment === "_next" ||
    metadataAssetSegments.has(lastSegment) ||
    /\.[a-z\d]{1,12}$/i.test(lastSegment) ||
    targetPathname === `/${DEFAULT_LOCALE}` ||
    targetPathname.startsWith(`/${DEFAULT_LOCALE}/`)
  ) {
    return { kind: "pass" };
  }

  return { kind: "redirect", pathname: targetPathname };
}
