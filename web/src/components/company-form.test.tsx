import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CompanyForm } from "@/components/company-form";
import { ApiClientError, api } from "@/lib/api";
import type { Company } from "@/lib/types";

const pendingCompany: Company = {
  id: "company-1",
  slug: "company-one",
  name: "Компания",
  unp: "123456789",
  address: "Минск",
  phone: "+375000000000",
  business_hours: null,
  status: "pending",
  revision: 1,
  moderation_reason: null
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

function render(company: Company | null = pendingCompany, companyRole: "owner" | "admin" | "seller" | "viewer" | null = "owner") {
  act(() => { root.render(createElement(CompanyForm, { initialCompany: company, companyRole })); });
}

function changeValue(element: HTMLInputElement | HTMLSelectElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(element), "value")?.set;
  setter?.call(element, value);
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
}

async function submit() {
  const form = container.querySelector<HTMLFormElement>("form");
  if (!form) throw new Error("Missing company form");
  await act(async () => {
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await Promise.resolve();
  });
}

describe("company pilot status", () => {
  it("caps company names at the API limit", () => {
    render();

    expect(container.querySelector<HTMLInputElement>('input[name="name"]')?.maxLength).toBe(180);
  });

  it("shows the API pending status as awaiting review", () => {
    render();

    const status = container.querySelector(".status-pill");
    expect(status?.textContent).toBe("На проверке");
    expect(status?.classList.contains("status-pending")).toBe(true);
    expect(status?.textContent).not.toBe("Доступ заблокирован");
  });

  it("shows the moderator reason when a company is rejected", () => {
    const rejectedCompany = {
      ...pendingCompany,
      status: "rejected",
      moderation_reason: "Уточните юридический адрес компании."
    } as Company;

    render(rejectedCompany);

    expect(container.querySelector('[role="alert"]')?.textContent).toContain("Уточните юридический адрес компании.");
  });

  it("sends the current company revision when saving changes", async () => {
    const update = vi.spyOn(api, "updateCompany").mockResolvedValue({ company: { ...pendingCompany, revision: 2 } });
    render();

    await submit();

    expect(update).toHaveBeenCalledWith("company-1", 1, {
      name: "Компания",
      unp: "123456789",
      address: "Минск",
      phone: "+375000000000",
      business_hours: null
    });
    expect(container.querySelector('.form-actions [aria-live="polite"]')?.textContent).toContain("Изменения сохранены.");
  });

  it("creates a company and immediately presents the pending review state", async () => {
    const create = vi.spyOn(api, "createCompany").mockResolvedValue({ company: pendingCompany });
    render(null);
    for (const [name, value] of Object.entries({ name: "Компания", unp: "123456789", address: "Минск, улица 1", phone: "+375291234567" })) {
      container.querySelector<HTMLInputElement>(`input[name="${name}"]`)!.value = value;
    }

    await submit();

    expect(create).toHaveBeenCalledWith({ name: "Компания", unp: "123456789", address: "Минск, улица 1", phone: "+375291234567", business_hours: null });
    expect(container.querySelector(".status-pill")?.textContent).toBe("На проверке");
    expect(container.querySelector('a[href^="/dealers/"]')).toBeNull();
    expect(container.querySelector('.form-actions [aria-live="polite"]')?.textContent).toContain("Заявка компании отправлена");
  });

  it("offers a real reload after a revision conflict", async () => {
    vi.spyOn(api, "updateCompany").mockRejectedValue(new ApiClientError(409, { code: "revision_conflict", message: "Устарела версия" }));
    const load = vi.spyOn(api, "company").mockResolvedValue({ company: { ...pendingCompany, revision: 2, status: "approved" } });
    render();

    await submit();

    expect(container.querySelector('[role="alert"]')?.textContent).toContain("изменились");
    const refresh = container.querySelector<HTMLButtonElement>('.company-error button');
    expect(refresh?.textContent).toContain("Загрузить актуальные сведения");
    await act(async () => { refresh?.dispatchEvent(new MouseEvent("click", { bubbles: true })); await Promise.resolve(); });

    expect(load).toHaveBeenCalledOnce();
    expect(container.querySelector(".status-pill")?.textContent).toBe("Допущена к пилоту");
    expect(container.querySelector('a[href="/dealers/company-one"]')).not.toBeNull();
  });

  it("links approved companies to the public page and disables blocked edits", () => {
    const approved = { ...pendingCompany, status: "approved" as const };
    render(approved);
    expect(container.querySelector('a[href="/dealers/company-one"]')?.textContent).toContain("Открыть страницу компании");
    expect(container.querySelector<HTMLButtonElement>('button[type="submit"]')?.disabled).toBe(false);

    const blocked = { ...approved, status: "blocked" as const };
    act(() => { root.render(createElement(CompanyForm, { key: "blocked", initialCompany: blocked })); });
    expect(container.querySelector<HTMLButtonElement>('button[type="submit"]')?.disabled).toBe(true);
  });

  it("lets an owner save the complete weekly business-hours schedule", async () => {
    const businessHours: NonNullable<Company["business_hours"]> = {
      mon: { open: "08:30", close: "17:30" },
      tue: { closed: true },
      wed: { closed: true },
      thu: { closed: true },
      fri: { closed: true },
      sat: { closed: true },
      sun: { closed: true }
    };
    const update = vi.spyOn(api, "updateCompany").mockResolvedValue({ company: { ...pendingCompany, business_hours: businessHours, revision: 2 } });
    render({ ...pendingCompany, business_hours: null }, "owner");

    const enableSchedule = container.querySelector<HTMLInputElement>('input[name="business_hours_enabled"]');
    expect(enableSchedule).not.toBeNull();
    await act(async () => { enableSchedule!.click(); });
    const mondayMode = container.querySelector<HTMLSelectElement>('select[name="business_hours.mon.mode"]');
    expect(mondayMode).not.toBeNull();
    await act(async () => { changeValue(mondayMode!, "open"); });
    const opening = container.querySelector<HTMLInputElement>('input[name="business_hours.mon.open"]');
    const closing = container.querySelector<HTMLInputElement>('input[name="business_hours.mon.close"]');
    expect(opening).not.toBeNull();
    expect(closing).not.toBeNull();
    await act(async () => { changeValue(opening!, "08:30"); changeValue(closing!, "17:30"); });

    await submit();

    expect(update).toHaveBeenCalledWith("company-1", 1, {
      name: "Компания", unp: "123456789", address: "Минск", phone: "+375000000000", business_hours: businessHours
    });
  });

  it.each(["seller", "viewer"] as const)("keeps company details and business hours read-only for a %s", (companyRole) => {
    render({ ...pendingCompany, business_hours: { mon: { open: "09:00", close: "18:00" }, tue: { closed: true }, wed: { closed: true }, thu: { closed: true }, fri: { closed: true }, sat: { closed: true }, sun: { closed: true } } }, companyRole);

    expect(container.querySelector<HTMLInputElement>('input[name="name"]')?.disabled).toBe(true);
    expect(container.querySelector<HTMLSelectElement>('select[name="business_hours.mon.mode"]')?.disabled).toBe(true);
    expect(container.querySelector<HTMLInputElement>('input[name="business_hours.mon.open"]')?.disabled).toBe(true);
    expect(container.querySelector<HTMLButtonElement>('button[type="submit"]')?.disabled).toBe(true);
    expect(container.textContent).toContain("Редактирование доступно владельцу или администратору компании");
  });

  it("shows backend business-hours validation next to the affected time field", async () => {
    vi.spyOn(api, "updateCompany").mockRejectedValue(new ApiClientError(422, {
      message: "Проверьте расписание.",
      field_errors: { "business_hours.mon.close": "Время закрытия должно быть позже времени открытия." }
    }));
    render({
      ...pendingCompany,
      business_hours: {
        mon: { open: "09:00", close: "08:00" },
        tue: { closed: true }, wed: { closed: true }, thu: { closed: true }, fri: { closed: true }, sat: { closed: true }, sun: { closed: true }
      }
    });

    await submit();

    const closing = container.querySelector<HTMLInputElement>('input[name="business_hours.mon.close"]');
    expect(closing?.getAttribute("aria-invalid")).toBe("true");
    expect(closing?.getAttribute("aria-describedby")).toBe("company-hours-mon-close-error");
    expect(container.querySelector("#company-hours-mon-close-error")?.textContent).toBe("Время закрытия должно быть позже времени открытия.");
  });
});
