import { describe, expect, it } from "vitest";
import { safeNextPath } from "@/lib/routing";

describe("safe login return path", () => {
  it("preserves a same-origin relative path, query, and hash", () => {
    expect(safeNextPath("/account/listings?status=draft#latest")).toBe("/account/listings?status=draft#latest");
  });

  it.each([
    "https://attacker.example/path",
    "//attacker.example/path",
    "/\\attacker.example/path",
    "/\n//attacker.example/path"
  ])("falls back for unsafe redirect targets: %s", (value) => {
    expect(safeNextPath(value)).toBe("/account");
  });

  it("falls back when no return path was provided", () => {
    expect(safeNextPath(undefined)).toBe("/account");
  });
});
