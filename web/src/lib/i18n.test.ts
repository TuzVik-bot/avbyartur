import { describe, expect, it } from "vitest";
import {
  DEFAULT_LOCALE,
  getMessage,
  isSupportedLocale,
  localeAliasResolution,
  localizedPath,
  SUPPORTED_LOCALES
} from "./i18n";

describe("Russian-only i18n scaffold", () => {
  it("exposes one supported locale and falls back to its dictionary", () => {
    expect(SUPPORTED_LOCALES).toEqual(["ru"]);
    expect(DEFAULT_LOCALE).toBe("ru");
    expect(isSupportedLocale("ru")).toBe(true);
    expect(isSupportedLocale("en")).toBe(false);
    expect(getMessage("header.cars")).toBe("Автомобили");
    expect(getMessage("header.cars", "en")).toBe("Автомобили");
    expect(getMessage("header.customsCalculator")).toBe("Таможенный калькулятор");
  });

  it("maps explicit Russian paths to the current unprefixed canonical route", () => {
    expect(localizedPath("/cars", "ru")).toBe("/cars");
    expect(localizedPath("/customs-calculator", "ru")).toBe("/customs-calculator");
    expect(localizedPath("/ru/cars", "ru")).toBe("/cars");
    expect(localizedPath("/ru", "ru")).toBe("/");
    expect(() => localizedPath("/cars", "en")).toThrow(/Unsupported locale/);
  });

  it.each([
    ["/ru", "/"],
    ["/ru/", "/"],
    ["/ru/cars", "/cars"],
    ["/ru/cars/", "/cars/"],
  ])("resolves a safe Russian alias %s to %s", (path, pathname) => {
    expect(localeAliasResolution(path)).toEqual({ kind: "redirect", pathname });
  });

  it.each([
    "/cars",
    "/en/cars",
    "/rufoo/cars",
    "/ru/api/v1/listings",
    "/ru/_next/static/chunk.js",
    "/ru/favicon.ico",
    "/ru/vehicles/silver-wagon.png",
    "/ru/icon",
    "/ru/apple-icon",
    "/ru/manifest",
    "/ru//cars",
    "/ru/cars%2fother",
    "/ru/cars%5cother",
    "/ru/cars/%2e%2e/admin",
    "/ru/cars/../admin",
    "//ru/cars",
  ])("does not redirect an unsafe, reserved, or non-locale path: %s", (path) => {
    expect(localeAliasResolution(path).kind).not.toBe("redirect");
  });

  it("rejects a raw backslash in the alias URL path", () => {
    expect(localeAliasResolution("/ru/cars", "http://localhost/ru\\cars").kind).toBe("pass");
  });

  it.each(["/ru/cars%2fother", "/ru/cars%5cother", "/ru/cars/%2e%2e/admin", "/cars/../admin"]) (
    "rejects unsafe URL construction for %s",
    (path) => expect(() => localizedPath(path, "ru")).toThrow()
  );
});
