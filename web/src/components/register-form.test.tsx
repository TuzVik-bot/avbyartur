import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RegisterForm } from "@/components/register-form";
import { ApiClientError, api, type AuthCapabilities } from "@/lib/api";
import type { AuthSession } from "@/lib/types";

const mocks = vi.hoisted(() => ({
  setSession: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn()
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: mocks.replace, refresh: mocks.refresh }) }));
vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a>
}));
vi.mock("@/components/auth-provider", () => ({ useAuth: () => ({ setSession: mocks.setSession }) }));

const enabled: AuthCapabilities = { sms_login: false, sms_registration: false, email_registration: true, email_verification: false, password_recovery: false };
const versions = { terms: "terms-2", privacy: "privacy-3" };
const session: AuthSession = {
  user: { id: "user-1", email: "new@example.com", display_name: "Новый", role: "user", company_id: null },
  csrf_token: "csrf-token"
};

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
  mocks.setSession.mockReset();
  mocks.replace.mockReset();
  mocks.refresh.mockReset();
  vi.restoreAllMocks();
});

async function render(capabilities: AuthCapabilities = enabled, consentVersions: typeof versions | null = versions) {
  vi.spyOn(api, "authCapabilities").mockResolvedValue(capabilities);
  await act(async () => {
    root.render(createElement(RegisterForm, { nextPath: "/account", consentVersions }));
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

async function submit({ password = "long-enough-password", repeat = "", consent = true }: { password?: string; repeat?: string; consent?: boolean } = {}) {
  repeat ||= password;
  const form = container.querySelector<HTMLFormElement>("form");
  if (!form) throw new Error("Missing registration form");
  form.querySelector<HTMLInputElement>('input[name="display_name"]')!.value = "Новый";
  form.querySelector<HTMLInputElement>('input[name="email"]')!.value = "new@example.com";
  form.querySelector<HTMLInputElement>('input[name="password"]')!.value = password;
  form.querySelector<HTMLInputElement>('input[name="password_repeat"]')!.value = repeat;
  form.querySelector<HTMLInputElement>('input[name="accept_terms"]')!.checked = consent;
  form.querySelector<HTMLInputElement>('input[name="accept_privacy"]')!.checked = consent;
  await act(async () => {
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

describe("registration form", () => {
  it("registers with the published consent versions and opens the session", async () => {
    const register = vi.spyOn(api, "register").mockResolvedValue(session);
    await render();

    await submit();

    expect(register).toHaveBeenCalledWith({
      email: "new@example.com", password: "long-enough-password", display_name: "Новый",
      accept_terms: true, accept_privacy: true, terms_version: "terms-2", privacy_version: "privacy-3"
    });
    expect(mocks.setSession).toHaveBeenCalledWith(session);
    expect(mocks.replace).toHaveBeenCalledWith("/account");
  });

  it("checks the password repeat and consent before calling the API", async () => {
    const register = vi.spyOn(api, "register");
    await render();

    await submit({ repeat: "another-long-password" });
    expect(container.querySelector('[role="alert"]')?.textContent).toBe("Пароли не совпадают.");

    await submit({ consent: false });
    expect(container.querySelector('[role="alert"]')?.textContent).toBe("Для регистрации подтвердите согласие с документами.");
    expect(register).not.toHaveBeenCalled();
  });

  it("explains a duplicate email without navigating", async () => {
    vi.spyOn(api, "register").mockRejectedValue(new ApiClientError(409, { code: "email_taken" }));
    await render();

    await submit();

    expect(container.querySelector('[role="alert"]')?.textContent).toContain("Аккаунт с этой почтой уже есть");
    expect(mocks.replace).not.toHaveBeenCalled();
  });

  it("shows a closed notice instead of the form when registration is disabled", async () => {
    await render({ ...enabled, email_registration: false });

    expect(container.querySelector("form")).toBeNull();
    expect(container.textContent).toContain("Регистрация сейчас закрыта");
    expect(container.querySelector('a[href="/login"]')).not.toBeNull();
  });

  it("does not offer the form without approved document versions", async () => {
    await render(enabled, null);

    expect(container.querySelector("form")).toBeNull();
    expect(container.textContent).toContain("утверждённые версии документов не опубликованы");
  });
});
