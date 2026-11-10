import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ pathname: "/cars", consent: "granted" as "granted" | "denied" | "unknown", pathnameCalls: 0 }));
vi.mock("next/navigation", () => ({ usePathname: () => { state.pathnameCalls += 1; return state.pathname; } }));
vi.mock("./contact-click-consent", () => ({ useContactClickConsent: () => ({ consent: state.consent, setConsent: vi.fn() }) }));

import { MeasurementProvider } from "./measurement-provider";

const ID = "G-TEST12345";
let root: Root;

function gtagScripts() {
  return document.head.querySelectorAll('script[src^="https://www.googletagmanager.com/gtag/js"]');
}

async function render(measurementId?: string) {
  const host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  await act(async () => root.render(<MeasurementProvider measurementId={measurementId}><p>content</p></MeasurementProvider>));
}

describe("measurement provider", () => {
  beforeEach(() => {
    state.pathname = "/cars";
    state.consent = "granted";
    state.pathnameCalls = 0;
  });
  afterEach(() => {
    act(() => root.unmount());
    document.body.replaceChildren();
    document.head.querySelectorAll("script").forEach((script) => script.remove());
  });

  it("loads Google Analytics with the configured ID after consent on public pages", async () => {
    await render(ID);
    const scripts = gtagScripts();
    expect(scripts).toHaveLength(1);
    expect(scripts[0].getAttribute("src")).toBe(`https://www.googletagmanager.com/gtag/js?id=${ID}`);
    expect((window as unknown as Record<string, unknown>)[`ga-disable-${ID}`]).toBe(false);
  });

  it("does not load Google Analytics without consent", async () => {
    state.consent = "unknown";
    await render(ID);
    expect(gtagScripts()).toHaveLength(0);
  });

  it("reads the pathname on every render, also before consent (stable hook order)", async () => {
    state.consent = "unknown";
    await render(ID);
    expect(state.pathnameCalls).toBeGreaterThan(0);
  });

  it.each(["/admin/monitoring", "/account", "/moderation", "/recover", "/verify-email", "/login"])("never loads Google Analytics on private path %s", async (pathname) => {
    state.pathname = pathname;
    await render(ID);
    expect(gtagScripts()).toHaveLength(0);
  });

  it("disables measurement when navigating from a public page into a private section", async () => {
    await render(ID);
    expect(gtagScripts()).toHaveLength(1);
    state.pathname = "/account/listings";
    await act(async () => root.render(<MeasurementProvider measurementId={ID}><p>content</p></MeasurementProvider>));
    expect(gtagScripts()).toHaveLength(0);
    expect((window as unknown as Record<string, unknown>)[`ga-disable-${ID}`]).toBe(true);
  });

  it("sends only the origin as page location, never the query or fragment", async () => {
    window.history.replaceState(null, "", "/cars?q=private-search#section");
    await render(ID);
    const config = (window.dataLayer ?? []).map((entry) => Array.from(entry as ArrayLike<unknown>)).find((args) => args[0] === "config");
    expect(config?.[2]).toMatchObject({ page_location: window.location.origin, send_page_view: false });
    window.history.replaceState(null, "", "/");
  });
});
