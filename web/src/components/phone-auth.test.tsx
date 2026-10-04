import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PhoneAuth } from "@/components/phone-auth";
import { api } from "@/lib/api";
import type { AuthSession } from "@/lib/types";

const mocks = vi.hoisted(() => ({ setSession: vi.fn(), replace: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: mocks.replace, refresh: mocks.refresh }) }));
vi.mock("@/components/auth-provider", () => ({ useAuth: () => ({ setSession: mocks.setSession }) }));

let container: HTMLDivElement;
let root: Root;

const capabilities = { sms_login: true, sms_registration: true, email_registration: false, email_verification: false, password_recovery: false };
const session: AuthSession = {
  user: { id: "phone-user-1", email: null, display_name: "Водитель", role: "user", company_id: null }, csrf_token: "phone-csrf"
};

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
  mocks.setSession.mockReset();
  mocks.replace.mockReset();
  mocks.refresh.mockReset();
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

async function render(value = capabilities, consentVersions: { terms: string; privacy: string } | null = null) {
  await act(async () => {
    root.render(createElement(PhoneAuth, { nextPath: "/account", capabilities: value, loadingCapabilities: false, consentVersions }));
    await Promise.resolve();
  });
}

function setValue<T extends HTMLInputElement>(element: T, value: string) {
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(element), "value")?.set;
  setter?.call(element, value);
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
}

describe("phone authentication", () => {
  it("requests a login code, verifies it, and installs the returned session", async () => {
    const send = vi.spyOn(api, "requestLoginOtp").mockResolvedValue({ accepted: true });
    const verify = vi.spyOn(api, "verifyPhoneOtp").mockResolvedValue(session);
    await render();

    const phone = container.querySelector<HTMLInputElement>('input[name="phone"]')!;
    const requestForm = phone.closest("form")!;
    await act(async () => {
      setValue(phone, "+375291234567");
      requestForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(send).toHaveBeenCalledWith("+375291234567");
    expect(container.textContent).toContain("код отправлен");

    const code = container.querySelector<HTMLInputElement>('input[name="code"]')!;
    await act(async () => {
      setValue(code, "123456");
      code.closest("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(verify).toHaveBeenCalledWith("+375291234567", "123456");
    expect(mocks.setSession).toHaveBeenCalledWith(session);
    expect(mocks.replace).toHaveBeenCalledWith("/account");
    expect(mocks.refresh).toHaveBeenCalledOnce();
  });

  it("sends accepted policy flags for phone registration and hides unavailable methods", async () => {
    const send = vi.spyOn(api, "requestRegistrationOtp").mockResolvedValue({ accepted: true });
    await render(capabilities, { terms: "terms-2", privacy: "privacy-3" });
    const registration = [...container.querySelectorAll("button")].find((button) => button.textContent === "Создать аккаунт");
    await act(async () => { registration?.click(); });
    const form = container.querySelector("form")!;
    const displayName = form.querySelector<HTMLInputElement>('input[name="display_name"]')!;
    const phone = form.querySelector<HTMLInputElement>('input[name="phone"]')!;
    const terms = form.querySelector<HTMLInputElement>('input[name="accept_terms"]')!;
    const privacy = form.querySelector<HTMLInputElement>('input[name="accept_privacy"]')!;
    await act(async () => {
      setValue(displayName, "Водитель");
      setValue(phone, "+375291234567");
      terms.checked = true;
      privacy.checked = true;
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(send).toHaveBeenCalledWith({ phone: "+375291234567", display_name: "Водитель", accept_terms: true, accept_privacy: true, terms_version: "terms-2", privacy_version: "privacy-3" });

    vi.restoreAllMocks();
    act(() => root.unmount());
    container.innerHTML = "";
    act(() => { root = createRoot(container); });
    await render({ ...capabilities, sms_login: false, sms_registration: false });
    expect(container.querySelector(".phone-auth")).toBeNull();
  });

  it("does not offer SMS registration without published legal consent versions", async () => {
    await render();
    expect(container.textContent).toContain("Регистрация по SMS сейчас недоступна");
    expect([...container.querySelectorAll("button")].some((button) => button.textContent === "Создать аккаунт")).toBe(false);
    expect(container.textContent).toContain("Вход по SMS");
  });
});
