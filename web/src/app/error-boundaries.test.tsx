import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({ default: ({ children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => createElement("a", props, children) }));

import AppError from "./error";
import CarsError from "./cars/error";
import DealersError from "./dealers/error";
import AccountError from "./account/error";

const boundaries = [AppError, CarsError, DealersError, AccountError];
let root: Root | undefined;
let container: HTMLDivElement | undefined;

afterEach(() => {
  if (root) act(() => root?.unmount());
  root = undefined;
  container?.remove();
  container = undefined;
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

describe("route error reporting", () => {
  it.each(boundaries)("reports only safe metadata from %s", async (Boundary) => {
    vi.stubEnv("NEXT_PUBLIC_RELEASE_ID", "release-2026.10");
    const error = Object.assign(new TypeError("secret contact and query data"), { digest: "private-digest" });
    const fetcher = vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true } as Response);
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(createElement(Boundary, { error, reset: () => {} }));
    });

    expect(fetcher).toHaveBeenCalledOnce();
    const [url, init] = fetcher.mock.calls[0];
    expect(url).toBe("/api/v1/analytics/errors");
    expect(JSON.parse(String(init?.body))).toEqual({
      error_type: "TypeError",
      release_id: "release-2026.10",
      breadcrumbs: [],
    });
    expect(String(init?.body)).not.toContain("secret");
    expect(String(init?.body)).not.toContain("private-digest");
    consoleSpy.mockRestore();
  });

  it.each([undefined, "https://private.invalid/release"]) ("does not report with absent or invalid release ID: %s", async (releaseId) => {
    vi.stubEnv("NEXT_PUBLIC_RELEASE_ID", releaseId);
    const fetcher = vi.spyOn(globalThis, "fetch");
    vi.spyOn(console, "error").mockImplementation(() => {});
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(createElement(AppError, { error: new Error("private"), reset: () => {} }));
    });

    expect(fetcher).not.toHaveBeenCalled();
  });

  it("does not report an error class outside the allowlist", async () => {
    vi.stubEnv("NEXT_PUBLIC_RELEASE_ID", "release-2026.10");
    const fetcher = vi.spyOn(globalThis, "fetch");
    vi.spyOn(console, "error").mockImplementation(() => {});
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
    const error = Object.assign(new Error("private"), { name: "PrivateError" });

    await act(async () => {
      root?.render(createElement(AppError, { error, reset: () => {} }));
    });

    expect(fetcher).not.toHaveBeenCalled();
  });
});
