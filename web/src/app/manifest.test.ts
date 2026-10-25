import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import manifest from "./manifest";

describe("web app manifest", () => {
  it("uses the public catalog as the standalone install entry point", () => {
    expect(manifest()).toMatchObject({
      name: "Авторынок BY",
      short_name: "Авторынок",
      start_url: "/cars",
      scope: "/",
      display: "standalone",
      prefer_related_applications: false
    });
  });

  it("advertises real any-purpose and maskable icons at install sizes", () => {
    expect(manifest().icons).toEqual(expect.arrayContaining([
      expect.objectContaining({ src: "/pwa-icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" }),
      expect.objectContaining({ src: "/pwa-icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" }),
      expect.objectContaining({ src: "/pwa-icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" })
    ]));

    for (const [file, dimension] of [["pwa-icon-192.png", 192], ["pwa-icon-512.png", 512]] as const) {
      const png = readFileSync(join(process.cwd(), "public", file));
      expect(png.subarray(0, 8)).toEqual(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]));
      expect(png.readUInt32BE(16)).toBe(dimension);
      expect(png.readUInt32BE(20)).toBe(dimension);
    }
  });
});
