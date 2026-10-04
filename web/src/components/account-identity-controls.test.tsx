import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AccountIdentityControls } from "@/components/account-identity-controls";
import { api, type ConsentHistoryItem, type UserProfile } from "@/lib/api";

const mocks = vi.hoisted(() => ({ setSession: vi.fn(), refresh: vi.fn() }));
vi.mock("next/link", () => ({ default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a> }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: mocks.refresh }) }));
vi.mock("@/components/auth-provider", () => ({ useAuth: () => ({ user: { email: "pilot@example.test" }, setSession: mocks.setSession }) }));

const profile: UserProfile = {
  id: "profile-1", display_name: "Пилот",
  contacts: { email: { masked: "p***@example.test", verified: false }, phone: { masked: "+375 ** ***-**-67", verified: true } }
};
const consents: ConsentHistoryItem[] = [{ document_type: "terms", version: "2026-01", accepted_at: "2026-10-01T08:00:00Z", source: "sms_registration" }];

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
  mocks.setSession.mockReset();
  mocks.refresh.mockReset();
  vi.spyOn(api, "authCapabilities").mockResolvedValue({ sms_login: false, sms_registration: false, email_registration: false, email_verification: true, password_recovery: true });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

async function render() {
  await act(async () => {
    root.render(createElement(AccountIdentityControls, { initialProfile: profile, initialConsents: consents }));
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

describe("account identity controls", () => {
  it("updates only the profile display name and shows masked contacts and consent history", async () => {
    await render();
    const update = vi.spyOn(api, "updateProfile").mockResolvedValue({ profile: { ...profile, display_name: "Новое имя" } });
    const input = container.querySelector<HTMLInputElement>('input[name="display_name"]')!;
    const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), "value")?.set;
    const form = input.closest("form")!;
    await act(async () => {
      setter?.call(input, "Новое имя");
      input.dispatchEvent(new Event("input", { bubbles: true }));
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(update).toHaveBeenCalledWith("Новое имя");
    expect(container.textContent).toContain("p***@example.test");
    expect(container.textContent).toContain("История согласий");
    expect(container.textContent).toContain("sms_registration");
    expect(mocks.refresh).toHaveBeenCalledOnce();
  });

  it("requires explicit deletion confirmation and reports the deactivation result", async () => {
    await render();
    const remove = vi.spyOn(api, "requestAccountDeletion").mockResolvedValue({ status: "requested", revoked_sessions: 2, withdrawn_listings: 3 });
    const form = container.querySelector<HTMLFormElement>(".account-deletion-form")!;
    await act(async () => { form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });
    expect(remove).not.toHaveBeenCalled();
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("Подтвердите");

    const checkbox = form.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
    await act(async () => {
      checkbox.click();
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(remove).toHaveBeenCalledOnce();
    expect(mocks.setSession).toHaveBeenCalledWith(null);
    expect(container.textContent).toContain("Аккаунт деактивирован");
    expect(container.textContent).toContain("Отозвано сеансов: 2");
    expect(container.textContent).toContain("Снято с публикации объявлений: 3");
  });

  it("verifies both phone numbers before changing the profile contact", async () => {
    const request = vi.spyOn(api, "requestPhoneChange").mockResolvedValue({
      accepted: true,
      challenge_id: "challenge-1",
      old_phone_masked: "+375 ** ***-**-67",
      new_phone_masked: "+375 ** ***-**-12",
      expires_in_seconds: 600
    });
    const confirm = vi.spyOn(api, "confirmPhoneChange").mockResolvedValue({ changed: true });
    await render();

    const phone = container.querySelector<HTMLInputElement>('input[name="new_phone"]')!;
    const requestForm = phone.closest("form")!;
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(phone), "value")?.set;
      setter?.call(phone, "+375291234512");
      phone.dispatchEvent(new Event("input", { bubbles: true }));
      requestForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(request).toHaveBeenCalledWith("+375291234512");
    expect(container.textContent).toContain("+375 ** ***-**-67");

    const confirmForm = container.querySelector<HTMLFormElement>('form[data-phone-change-confirm]')!;
    const oldCode = confirmForm.querySelector<HTMLInputElement>('input[name="old_code"]')!;
    const newCode = confirmForm.querySelector<HTMLInputElement>('input[name="new_code"]')!;
    const setter = (input: HTMLInputElement, value: string) => Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), "value")?.set?.call(input, value);
    await act(async () => {
      setter(oldCode, "123456"); setter(newCode, "654321");
      oldCode.dispatchEvent(new Event("input", { bubbles: true })); newCode.dispatchEvent(new Event("input", { bubbles: true }));
      confirmForm.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(confirm).toHaveBeenCalledWith("challenge-1", "123456", "654321");
    expect(container.textContent).toContain("Номер телефона изменён");
  });
});
