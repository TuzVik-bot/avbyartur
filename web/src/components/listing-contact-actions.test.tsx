import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { ListingContactActions } from "@/components/listing-contact-actions";

const props = { active: true, guestContactRevealEnabled: false, phone: "", busy: false, error: "", onReveal: vi.fn() };

describe("listing contact channels", () => {
  it("does not expose messenger links before the phone contact is revealed", () => {
    const html = renderToStaticMarkup(createElement(ListingContactActions, { ...props, messengers: [{ channel: "telegram", uri: "https://t.me/seller", opted_in: true }] }));
    expect(html).not.toContain("t.me");
    expect(html).toContain("Показать телефон");
  });

  it("shows only opted-in channels with provider-approved HTTPS addresses after reveal", () => {
    const html = renderToStaticMarkup(createElement(ListingContactActions, { ...props, phone: "+375290000000", messengers: [
      { channel: "telegram", uri: "https://t.me/seller", opted_in: true },
      { channel: "viber", uri: "viber://chat?number=375290000000", opted_in: true },
      { channel: "telegram", uri: "https://t.me/not-opted-in", opted_in: false }
    ] }));
    expect(html).toContain("Telegram");
    expect(html).toContain("href=\"https://t.me/seller\"");
    expect(html).not.toContain("Viber");
    expect(html).not.toContain("not-opted-in");
  });

  it("does not render contact actions for non-active listings", () => {
    const html = renderToStaticMarkup(createElement(ListingContactActions, { ...props, active: false }));
    expect(html).toContain("Контакт недоступен");
    expect(html).not.toContain("Показать телефон");
  });
});
