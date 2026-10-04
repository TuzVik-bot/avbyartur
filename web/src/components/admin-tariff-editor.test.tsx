import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AdminTariffEditor } from "@/components/admin-tariff-editor";
import { adminTariffsApi, type AdminTariff } from "@/lib/admin-tariffs";
import { ApiClientError } from "@/lib/api";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const tariff: AdminTariff = {
  id: "tariff-1", code: "bump-7-days", service_code: "bump", name: "Поднять объявление",
  amount: "12.34", currency: "BYN", duration_days: 7, listing_quota: null,
  status: "disabled", revision: 1, created_at: "2026-10-01T10:00:00Z", updated_at: "2026-10-01T10:00:00Z"
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

function setValue(element: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(element), "value")?.set;
  setter?.call(element, value);
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
}

describe("admin tariff editor", () => {
  it("keeps the editor open and explains a stale revision returned by the API", async () => {
    const update = vi.spyOn(adminTariffsApi, "update").mockRejectedValue(
      new ApiClientError(409, { code: "revision_conflict", message: "Тариф изменён; обновите список" })
    );
    act(() => root.render(createElement(AdminTariffEditor, { initialTariffs: [tariff], initialError: false })));
    const card = container.querySelector<HTMLElement>(".admin-tariff-card")!;
    await act(async () => {
      [...card.querySelectorAll("button")].find((button) => button.textContent?.includes("Изменить тариф"))!.click();
    });
    const form = card.querySelector<HTMLFormElement>(".admin-tariff-form")!;
    setValue(form.querySelector<HTMLInputElement>('input[name="amount"]')!, "25.67");
    setValue(form.querySelector<HTMLTextAreaElement>('textarea[name="reason"]')!, "Согласована новая цена");
    setValue(form.querySelector<HTMLInputElement>('input[name="current_password"]')!, "step-up-password");
    setValue(form.querySelector<HTMLInputElement>('input[name="confirmation"]')!, "UPDATE_TARIFF");

    await act(async () => {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(update).toHaveBeenCalledWith("tariff-1", {
      name: "Поднять объявление", amount: "25.67", currency: "BYN", duration_days: 7,
      listing_quota: null, status: "disabled", expected_revision: 1,
      reason: "Согласована новая цена", confirmation: "UPDATE_TARIFF", current_password: "step-up-password"
    });
    expect(form.isConnected).toBe(true);
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("Тариф уже изменён");
    expect(form.querySelector<HTMLInputElement>('input[name="amount"]')?.value).toBe("25.67");
  });

  it("rejects fractional precision beyond two decimal places before sending a price", async () => {
    const create = vi.spyOn(adminTariffsApi, "create");
    act(() => root.render(createElement(AdminTariffEditor, { initialTariffs: [], initialError: false })));
    await act(async () => {
      [...container.querySelectorAll("button")].find((button) => button.textContent?.includes("Создать тариф"))!.click();
    });
    const form = container.querySelector<HTMLFormElement>(".admin-tariff-form")!;
    setValue(form.querySelector<HTMLInputElement>('input[name="amount"]')!, "12.345");
    setValue(form.querySelector<HTMLTextAreaElement>('textarea[name="reason"]')!, "Утверждённая тестовая цена");
    setValue(form.querySelector<HTMLInputElement>('input[name="current_password"]')!, "step-up-password");
    setValue(form.querySelector<HTMLInputElement>('input[name="confirmation"]')!, "CREATE_TARIFF");
    await act(async () => { form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });

    expect(create).not.toHaveBeenCalled();
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("двумя знаками после запятой");
  });

  it("explains why a tariff with order history cannot be deleted", async () => {
    const remove = vi.spyOn(adminTariffsApi, "delete").mockRejectedValue(
      new ApiClientError(409, { code: "tariff_referenced", message: "Тариф связан с историей заказов" })
    );
    act(() => root.render(createElement(AdminTariffEditor, { initialTariffs: [tariff], initialError: false })));
    const card = container.querySelector<HTMLElement>(".admin-tariff-card")!;
    await act(async () => {
      [...card.querySelectorAll("button")].find((button) => button.textContent?.includes("Удалить неиспользуемый"))!.click();
    });
    const form = card.querySelector<HTMLFormElement>(".admin-tariff-form")!;
    setValue(form.querySelector<HTMLTextAreaElement>('textarea[name="reason"]')!, "Причина удаления тарифа");
    setValue(form.querySelector<HTMLInputElement>('input[name="current_password"]')!, "step-up-password");
    setValue(form.querySelector<HTMLInputElement>('input[name="confirmation"]')!, "DELETE_TARIFF");
    await act(async () => {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(remove).toHaveBeenCalledWith("tariff-1", {
      expected_revision: 1, reason: "Причина удаления тарифа", confirmation: "DELETE_TARIFF", current_password: "step-up-password"
    });
    expect(form.isConnected).toBe(true);
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("историей заказов");
  });
});
