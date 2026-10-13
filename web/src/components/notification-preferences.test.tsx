import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NotificationPreferences } from "@/components/notification-preferences";
import { api } from "@/lib/api";

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

describe("notification preferences", () => {
  it("saves global web and email choices with the expected revision", async () => {
    const save = vi.spyOn(api, "updateNotificationPreferences").mockResolvedValue({ preferences: {
      web_enabled: false, email_enabled: true, revision: 5, email_verified: true, email_delivery_configured: true
    } });
    await act(async () => {
      root.render(createElement(NotificationPreferences, { initialPreferences: {
        web_enabled: true, email_enabled: false, revision: 4, email_verified: true, email_delivery_configured: true
      } }));
    });

    const web = container.querySelector<HTMLInputElement>('input[name="web_enabled"]')!;
    const email = container.querySelector<HTMLInputElement>('input[name="email_enabled"]')!;
    await act(async () => {
      web.click(); email.click();
    });
    const form = web.closest("form")!;
    await act(async () => {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(save).toHaveBeenCalledWith({ web_enabled: false, email_enabled: true, expected_revision: 4 });
    expect(container.textContent).toContain("Настройки уведомлений сохранены");
  });

  it("explains that email delivery requires a verified address", async () => {
    await act(async () => {
      root.render(createElement(NotificationPreferences, { initialPreferences: {
        web_enabled: true, email_enabled: false, revision: 0, email_verified: false, email_delivery_configured: true
      } }));
    });

    expect(container.textContent).toContain("Подтвердите адрес электронной почты в настройках профиля");
    expect(container.querySelector<HTMLInputElement>('input[name="web_enabled"]')?.checked).toBe(true);
  });

  it("reports email as unavailable when delivery is not configured", async () => {
    await act(async () => {
      root.render(createElement(NotificationPreferences, { initialPreferences: {
        web_enabled: true, email_enabled: false, revision: 0, email_verified: true, email_delivery_configured: false
      } }));
    });

    expect(container.textContent).toContain("Email-уведомления пока недоступны: почтовая доставка не настроена.");
  });

  it("reports email as available only when the address and delivery are ready", async () => {
    await act(async () => {
      root.render(createElement(NotificationPreferences, { initialPreferences: {
        web_enabled: true, email_enabled: false, revision: 0, email_verified: true, email_delivery_configured: true
      } }));
    });

    expect(container.textContent).toContain("Email-уведомления доступны для подтверждённого адреса.");
  });
});
