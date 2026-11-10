import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  authCapabilities: vi.fn(),
  confirmPasswordRecovery: vi.fn(),
  requestPasswordRecovery: vi.fn(),
}));
vi.mock("@/lib/api", () => ({ api: mocks }));

import { PasswordRecoveryForm } from "./password-recovery-form";

let root: Root;

async function render(token?: string) {
  const host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  await act(async () => root.render(<PasswordRecoveryForm token={token} />));
}

function fill(name: string, value: string) {
  const input = document.querySelector(`input[name=${name}]`) as HTMLInputElement;
  input.value = value;
}

describe("password recovery token handling", () => {
  beforeEach(() => {
    mocks.authCapabilities.mockResolvedValue({ password_recovery: true, test_mail: false });
    mocks.confirmPasswordRecovery.mockResolvedValue(undefined);
    window.history.replaceState(null, "", "/recover?token=secret-recovery-token");
  });
  afterEach(() => {
    act(() => root.unmount());
    document.body.replaceChildren();
    window.history.replaceState(null, "", "/");
  });

  it("removes the token from the address bar right after reading it", async () => {
    await render("secret-recovery-token");
    expect(window.location.search).toBe("");
    expect(window.location.href).not.toContain("secret-recovery-token");
    expect(window.location.pathname).toBe("/recover");
  });

  it("keeps the token in component state and submits it", async () => {
    await render("secret-recovery-token");
    fill("new_password", "new-password-1");
    fill("confirm_password", "new-password-1");
    await act(async () => (document.querySelector("form") as HTMLFormElement).requestSubmit());
    expect(mocks.confirmPasswordRecovery).toHaveBeenCalledWith("secret-recovery-token", "new-password-1");
    expect(document.body.textContent).toContain("Пароль изменён");
  });

  it("leaves the address untouched when no token is present", async () => {
    window.history.replaceState(null, "", "/recover?from=login");
    await render();
    expect(window.location.search).toBe("?from=login");
  });
});
