import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ confirmEmailVerification: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: mocks }));

import { EmailVerificationConfirm } from "./email-verification-confirm";

let root: Root;

async function render(token?: string) {
  const host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  await act(async () => root.render(<EmailVerificationConfirm token={token} />));
}

describe("email verification token handling", () => {
  beforeEach(() => {
    mocks.confirmEmailVerification.mockResolvedValue(undefined);
    window.history.replaceState(null, "", "/verify-email?token=secret-verify-token");
  });
  afterEach(() => {
    act(() => root.unmount());
    document.body.replaceChildren();
    window.history.replaceState(null, "", "/");
  });

  it("removes the token from the address bar right after reading it", async () => {
    await render("secret-verify-token");
    expect(window.location.search).toBe("");
    expect(window.location.href).not.toContain("secret-verify-token");
    expect(window.location.pathname).toBe("/verify-email");
  });

  it("keeps the token in component state and confirms with it", async () => {
    await render("secret-verify-token");
    await act(async () => (document.querySelector("form") as HTMLFormElement).requestSubmit());
    expect(mocks.confirmEmailVerification).toHaveBeenCalledWith("secret-verify-token");
    expect(document.body.textContent).toContain("Электронная почта подтверждена");
  });
});
