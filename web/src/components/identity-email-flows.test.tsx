import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EmailVerificationConfirm } from "@/components/email-verification-confirm";
import { PasswordRecoveryForm } from "@/components/password-recovery-form";
import { api } from "@/lib/api";

vi.mock("next/link", () => ({ default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a> }));

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

async function render(element: React.ReactNode) {
  await act(async () => { root.render(element); await Promise.resolve(); });
}

function setValue(element: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(element), "value")?.set;
  setter?.call(element, value);
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
}

describe("identity email flows", () => {
  it("keeps password recovery responses generic", async () => {
    vi.spyOn(api, "authCapabilities").mockResolvedValue({ sms_login: false, sms_registration: false, email_registration: false, email_verification: false, password_recovery: true });
    const request = vi.spyOn(api, "requestPasswordRecovery").mockResolvedValue({ accepted: true });
    await render(createElement(PasswordRecoveryForm, {}));
    const email = container.querySelector<HTMLInputElement>('input[name="email"]')!;
    const form = email.closest("form")!;
    await act(async () => {
      setValue(email, "person@example.test");
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(request).toHaveBeenCalledWith("person@example.test");
    expect(container.textContent).toContain("Если для этого адреса доступно восстановление");
    expect(container.textContent).not.toContain("person@example.test");
  });

  it("requires matching passwords before confirming a recovery token", async () => {
    vi.spyOn(api, "authCapabilities").mockResolvedValue({ sms_login: false, sms_registration: false, email_registration: false, email_verification: false, password_recovery: true });
    const confirm = vi.spyOn(api, "confirmPasswordRecovery").mockResolvedValue({ ok: true });
    await render(createElement(PasswordRecoveryForm, { token: "opaque-token" }));
    const form = container.querySelector("form")!;
    const password = form.querySelector<HTMLInputElement>('input[name="new_password"]')!;
    const repeated = form.querySelector<HTMLInputElement>('input[name="confirm_password"]')!;
    await act(async () => {
      setValue(password, "new-secret"); setValue(repeated, "different-secret");
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });
    expect(confirm).not.toHaveBeenCalled();
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("не совпадают");

    await act(async () => {
      setValue(password, "new-secret"); setValue(repeated, "new-secret");
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(confirm).toHaveBeenCalledWith("opaque-token", "new-secret");
    expect(container.textContent).toContain("Пароль изменён");
  });

  it("submits an email verification token only after the user confirms", async () => {
    const confirm = vi.spyOn(api, "confirmEmailVerification").mockResolvedValue({ verified: true });
    await render(createElement(EmailVerificationConfirm, { token: "email-token" }));
    expect(confirm).not.toHaveBeenCalled();
    const form = container.querySelector("form")!;
    await act(async () => {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(confirm).toHaveBeenCalledWith("email-token");
    expect(container.textContent).toContain("Электронная почта подтверждена");
  });

  it("reads and removes an email verification token from the URL fragment", async () => {
    const confirm = vi.spyOn(api, "confirmEmailVerification").mockResolvedValue({ verified: true });
    window.history.replaceState({}, "", "/verify-email#token=fragment-email-token");
    await render(createElement(EmailVerificationConfirm, {}));
    expect(window.location.hash).toBe("");
    const form = container.querySelector("form")!;
    await act(async () => {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(confirm).toHaveBeenCalledWith("fragment-email-token");
  });

  it("reads and removes a recovery token from the URL fragment", async () => {
    vi.spyOn(api, "authCapabilities").mockResolvedValue({ sms_login: false, sms_registration: false, email_registration: false, email_verification: false, password_recovery: true });
    const confirm = vi.spyOn(api, "confirmPasswordRecovery").mockResolvedValue({ ok: true });
    window.history.replaceState({}, "", "/recover#token=fragment-recovery-token");
    await render(createElement(PasswordRecoveryForm, {}));
    expect(window.location.hash).toBe("");
    const form = container.querySelector("form")!;
    const password = form.querySelector<HTMLInputElement>('input[name="new_password"]')!;
    const repeated = form.querySelector<HTMLInputElement>('input[name="confirm_password"]')!;
    await act(async () => {
      setValue(password, "new-password"); setValue(repeated, "new-password");
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(confirm).toHaveBeenCalledWith("fragment-recovery-token", "new-password");
  });
});
