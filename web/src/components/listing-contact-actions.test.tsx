import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
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
      { channel: "viber", uri: "https://viber.me/seller", opted_in: true },
      { channel: "viber", uri: "viber://chat?number=375290000000", opted_in: true },
      { channel: "telegram", uri: "https://telegram.org/sellername", opted_in: true },
      { channel: "telegram", uri: "https://t.me/sellername/extra", opted_in: true },
      { channel: "viber", uri: "https://chat.viber.com/seller", opted_in: true },
      { channel: "telegram", uri: "https://t.me/not-opted-in", opted_in: false }
    ] }));
    expect(html).toContain("Telegram");
    expect(html).toContain("href=\"https://t.me/seller\"");
    expect(html).toContain("Viber");
    expect(html).toContain("href=\"https://viber.me/seller\"");
    expect(html).not.toContain("href=\"viber://");
    expect(html).not.toContain("telegram.org");
    expect(html).not.toContain("/extra");
    expect(html).not.toContain("chat.viber.com");
    expect(html).not.toContain("not-opted-in");
  });

  it("does not render contact actions for non-active listings", () => {
    const html = renderToStaticMarkup(createElement(ListingContactActions, { ...props, active: false }));
    expect(html).toContain("Контакт недоступен");
    expect(html).not.toContain("Показать телефон");
  });

  it("reports phone, Telegram, and Viber only when their action is clicked", async () => {
    const host = document.createElement("div"); document.body.append(host);
    const root = createRoot(host);
    const onContactClick = vi.fn();
    await act(async () => root.render(createElement(ListingContactActions, { ...props, phone: "+375290000000", onContactClick, messengers: [
      { channel: "telegram", uri: "https://t.me/seller", opted_in: true },
      { channel: "viber", uri: "https://viber.me/seller", opted_in: true }
    ] })));
    host.querySelectorAll("a").forEach((link) => link.addEventListener("click", (event) => event.preventDefault()));
    host.querySelector<HTMLAnchorElement>('a[href^="tel:"]')!.click();
    host.querySelector<HTMLAnchorElement>('a[href="https://t.me/seller"]')!.click();
    host.querySelector<HTMLAnchorElement>('a[href="https://viber.me/seller"]')!.click();
    expect(onContactClick.mock.calls.map(([channel]) => channel)).toEqual(["phone", "telegram", "viber"]);
    root.unmount(); host.remove();
  });

  it("does not report the reveal action itself", async () => {
    const host = document.createElement("div"); document.body.append(host);
    const root = createRoot(host);
    const onContactClick = vi.fn();
    const onReveal = vi.fn();
    await act(async () => root.render(createElement(ListingContactActions, { ...props, onReveal, onContactClick })));
    host.querySelector<HTMLButtonElement>(".contact-reveal")!.click();
    expect(onReveal).toHaveBeenCalledOnce();
    expect(onContactClick).not.toHaveBeenCalled();
    root.unmount(); host.remove();
  });
});
