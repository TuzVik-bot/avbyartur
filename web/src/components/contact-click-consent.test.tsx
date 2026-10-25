import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it, beforeEach, afterEach } from "vitest";
import { ContactClickConsent, ContactClickConsentProvider, useContactClickConsent } from "./contact-click-consent";

function Probe() {
  const { consent } = useContactClickConsent();
  return <span data-consent={consent} />;
}

describe("contact click consent", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => document.body.replaceChildren());

  it("starts unknown and persists an explicit denial", () => {
    const host = document.createElement("div"); document.body.append(host);
    const root = createRoot(host);
    act(() => root.render(<ContactClickConsentProvider><Probe /><ContactClickConsent /></ContactClickConsentProvider>));
    expect(document.querySelector("[data-consent]")?.getAttribute("data-consent")).toBe("unknown");
    act(() => (document.querySelector("button[data-consent-choice=denied]") as HTMLButtonElement).click());
    expect(document.querySelector("[data-consent]")?.getAttribute("data-consent")).toBe("denied");
    expect(localStorage.getItem("avtorinok.contact_click_consent")).toBe("denied");
    root.unmount();
  });

  it("allows granting and revoking later", () => {
    localStorage.setItem("avtorinok.contact_click_consent", "granted");
    const host = document.createElement("div"); document.body.append(host);
    const root = createRoot(host);
    act(() => root.render(<ContactClickConsentProvider><Probe /><ContactClickConsent /></ContactClickConsentProvider>));
    expect(document.querySelector("[data-consent]")?.getAttribute("data-consent")).toBe("granted");
    act(() => (document.querySelector("button[data-consent-choice=denied]") as HTMLButtonElement).click());
    expect(localStorage.getItem("avtorinok.contact_click_consent")).toBe("denied");
    root.unmount();
  });
});
