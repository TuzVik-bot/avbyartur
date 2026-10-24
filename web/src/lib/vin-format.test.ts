import { describe, expect, it } from "vitest";
import { checkVinFormat } from "@/lib/vin-format";

describe("checkVinFormat", () => {
  it("accepts a standard 17-character VIN shape after trimming and case normalization", () => {
    expect(checkVinFormat("  1hgcm82633a004352 ")).toMatchObject({
      valid: true,
      normalized: "1HGCM82633A004352"
    });
  });

  it("rejects a wrong length without claiming to validate vehicle history", () => {
    const result = checkVinFormat("1HGCM82633A00435");

    expect(result.valid).toBe(false);
    expect(result.message).toContain("17 символов");
  });

  it.each(["I", "O", "Q"])("rejects the disallowed VIN character %s", (character) => {
    const result = checkVinFormat(`1HGCM82633A00435${character}`);

    expect(result.valid).toBe(false);
    expect(result.message).toContain("не используются");
  });
});
