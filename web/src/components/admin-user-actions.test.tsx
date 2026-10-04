import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AdminUserActions } from "@/components/admin-user-actions";
import { adminApi, type AdminUser } from "@/lib/admin";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const user: AdminUser = {
  id: "user-2",
  email: "person@example.test",
  display_name: "Пользователь",
  role: "user",
  status: "active",
  created_at: "2026-10-01T08:00:00Z"
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
  vi.restoreAllMocks();
});

function setValue<T extends HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>(element: T, value: string) {
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(element), "value")?.set;
  setter?.call(element, value);
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
}

describe("admin user actions", () => {
  it("requires password, reason, and explicit confirmation before sending expected user state", async () => {
    const updateUser = vi.spyOn(adminApi, "updateUser").mockResolvedValue({ user, changed: true });
    const onUpdated = vi.fn();
    act(() => { root.render(createElement(AdminUserActions, { user, currentUserId: "admin-1", onUpdated })); });

    const openButton = [...container.querySelectorAll("button")].find((button) => button.textContent?.includes("Изменить доступ"));
    await act(async () => { openButton?.click(); });
    const form = container.querySelector("form");
    expect(form).not.toBeNull();

    await act(async () => {
      form!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("пароль");
    expect(updateUser).not.toHaveBeenCalled();

    const role = form!.querySelector<HTMLSelectElement>('select[name="role"]')!;
    const status = form!.querySelector<HTMLSelectElement>('select[name="status"]')!;
    const password = form!.querySelector<HTMLInputElement>('input[name="current_password"]')!;
    const reason = form!.querySelector<HTMLTextAreaElement>('textarea[name="reason"]')!;
    const confirmation = form!.querySelector<HTMLInputElement>('input[name="confirmation"]')!;
    await act(async () => {
      setValue(role, "moderator");
      setValue(status, "blocked");
      setValue(password, "correct horse battery");
      setValue(reason, "Проверка доступа по обращению №42");
      confirmation.checked = true;
      confirmation.dispatchEvent(new Event("change", { bubbles: true }));
      form!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(updateUser).toHaveBeenCalledWith(user.id, {
      role: "moderator",
      status: "blocked",
      expected_role: "user",
      expected_status: "active",
      reason: "Проверка доступа по обращению №42",
      confirmation: "UPDATE_USER",
      current_password: "correct horse battery"
    });
    expect(onUpdated).toHaveBeenCalledOnce();
  });
});
