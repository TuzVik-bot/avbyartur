import { act, createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LoginForm } from "@/components/login-form";
import { ApiClientError, api } from "@/lib/api";
import type { AuthSession } from "@/lib/types";

const mocks = vi.hoisted(() => ({
  setSession: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn()
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: mocks.replace, refresh: mocks.refresh }) }));
vi.mock("@/components/auth-provider", () => ({ useAuth: () => ({ setSession: mocks.setSession }) }));

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
  vi.spyOn(api, "authCapabilities").mockResolvedValue({ sms_login: false, sms_registration: false, email_registration: false, email_verification: false, password_recovery: false });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  mocks.setSession.mockReset();
  mocks.replace.mockReset();
  mocks.refresh.mockReset();
  vi.restoreAllMocks();
});

function render(nextPath: string) {
  act(() => { root.render(createElement(LoginForm, { nextPath })); });
}

async function submit(email = "person@example.com", password = "secret") {
  const form = container.querySelector<HTMLFormElement>("form");
  if (!form) throw new Error("Missing login form");
  form.querySelector<HTMLInputElement>('input[name="email"]')!.value = email;
  form.querySelector<HTMLInputElement>('input[name="password"]')!.value = password;

  await act(async () => {
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

const session: AuthSession = {
  user: {
    id: "user-1",
    email: "person@example.com",
    display_name: "Пользователь",
    role: "user",
    company_id: null
  },
  csrf_token: "csrf-token"
};

describe("login form", () => {
  it("uses POST and keeps password submission disabled until hydration", () => {
    const html = renderToStaticMarkup(createElement(LoginForm, { nextPath: "/sell" }));

    expect(html).toContain('<form method="post">');
    expect(html).toMatch(/<button[^>]*type="submit"[^>]*disabled=""/);
  });

  it("sets the session, safely returns to the requested path, and refreshes", async () => {
    const login = vi.spyOn(api, "login").mockResolvedValue(session);
    render("/account/listings?status=draft#latest");

    await submit();

    expect(login).toHaveBeenCalledWith("person@example.com", "secret");
    expect(mocks.setSession).toHaveBeenCalledWith(session);
    expect(mocks.replace).toHaveBeenCalledWith("/account/listings?status=draft#latest");
    expect(mocks.refresh).toHaveBeenCalledOnce();
  });

  it("shows a generic credentials error after a 401 and does not navigate", async () => {
    vi.spyOn(api, "login").mockRejectedValue(new ApiClientError(401, {}));
    render("/account/listings");

    await submit();

    expect(container.querySelector('[role="alert"]')?.textContent).toBe("Проверьте адрес почты и пароль.");
    expect(mocks.setSession).not.toHaveBeenCalled();
    expect(mocks.replace).not.toHaveBeenCalled();
    expect(mocks.refresh).not.toHaveBeenCalled();
  });

  it("uses the account route for an unsafe next path", async () => {
    vi.spyOn(api, "login").mockResolvedValue(session);
    render("//attacker.example/path");

    await submit();

    expect(mocks.replace).toHaveBeenCalledWith("/account");
    expect(mocks.refresh).toHaveBeenCalledOnce();
  });
});

it("offers email registration when enabled with published consent versions", async () => {
  vi.mocked(api.authCapabilities).mockResolvedValue({ sms_login: false, sms_registration: false, email_registration: true, email_verification: false, password_recovery: false });
  await act(async () => { root.render(createElement(LoginForm, { nextPath: "/account", consentVersions: { terms: "v1", privacy: "v1" } })); });
  const button = [...container.querySelectorAll("button")].find(b => b.textContent === "Создать аккаунт");
  expect(button).toBeDefined();
  await act(async () => button!.click());
  expect(container.querySelector('input[name="display_name"]')).not.toBeNull();
  expect(container.querySelector('input[name="password"]')?.getAttribute("minlength")).toBe("10");
  expect(container.querySelector('input[name="accept_privacy"]')).not.toBeNull();
});

it("registers, starts a session and returns to listing creation", async () => {
  vi.mocked(api.authCapabilities).mockResolvedValue({ sms_login: false, sms_registration: false, email_registration: true, email_verification: false, password_recovery: false });
  vi.spyOn(api, "registerEmail").mockResolvedValue(session);
  await act(async () => { root.render(createElement(LoginForm, { nextPath: "/sell", consentVersions: { terms: "v1", privacy: "v1" } })); });
  await act(async () => { [...container.querySelectorAll("button")].find(b => b.textContent === "Создать аккаунт")!.click(); });
  container.querySelector<HTMLInputElement>('input[name="display_name"]')!.value = "Пользователь";
  container.querySelector<HTMLInputElement>('input[name="password_confirm"]')!.value = "Strong-password-123";
  container.querySelector<HTMLInputElement>('input[name="accept_terms"]')!.checked = true;
  container.querySelector<HTMLInputElement>('input[name="accept_privacy"]')!.checked = true;
  await submit("person@example.com", "Strong-password-123");
  expect(mocks.setSession).toHaveBeenCalledWith(session);
  expect(mocks.replace).toHaveBeenCalledWith("/sell");
  expect(mocks.refresh).toHaveBeenCalledOnce();
});

it("offers explicitly enabled temporary registration with its notice", async () => {
  vi.mocked(api.authCapabilities).mockResolvedValue({ sms_login: false, sms_registration: false, email_registration: true, email_registration_pilot: true, email_verification: false, password_recovery: false });
  await act(async () => { root.render(createElement(LoginForm, { nextPath: "/account", consentVersions: null })); });
  await act(async () => { [...container.querySelectorAll("button")].find(b => b.textContent === "Создать аккаунт")!.click(); });
  expect(container.textContent).toContain("Реквизиты оператора ещё не опубликованы");
  expect(container.querySelector('a[href="/registration-privacy"]')).not.toBeNull();
});
