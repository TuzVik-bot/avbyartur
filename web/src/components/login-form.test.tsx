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
  vi.spyOn(api, "authCapabilities").mockResolvedValue({ sms_login: false, sms_registration: false, email_verification: false, password_recovery: false });
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
