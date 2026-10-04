import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "@/components/auth-provider";
import { CompanyModerationActions, ListingModerationActions } from "@/components/moderation-actions";
import { api } from "@/lib/api";
import type { AuthSession, Company, Listing, User } from "@/lib/types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const company: Company = {
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

const listing = (status: Listing["status"]): Listing => ({
  id: "listing-1",
  slug: "listing-one",
  title: "Toyota Corolla",
  make: { id: "make-1", slug: "toyota", name: "Toyota" },
  model: { id: "model-1", slug: "corolla", name: "Corolla" },
  generation: null,
  year: 2020,
  mileage_km: 50000,
  fuel: "petrol",
  transmission: "automatic",
  drive: "front",
  body_type: "Седан",
  price: { amount: "10000", currency: "BYN" },
  region: { id: "region-1", slug: "minsk-region", name: "Минская область" },
  city: { id: "city-1", slug: "minsk", name: "Минск" },
  cover_url: null,
  seller: { type: "private", id: "user-1", name: "Продавец" },
  created_at: "2026-09-27T00:00:00Z",
  updated_at: "2026-09-27T00:00:00Z",
  damaged: false,
  parts_only: false,
  status,
  revision: 2,
  description: "",
  condition: "used",
  photo_urls: []
});

const session = (role: User["role"]): AuthSession => ({
  user: { id: "user-1", email: "pilot@example.test", display_name: "Пилот", role, company_id: null },
  csrf_token: "csrf-test"
});

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

describe("company moderation", () => {
  it("requires and sends a reason when blocking a company", async () => {
    const moderateCompany = vi.spyOn(api, "moderateCompany").mockResolvedValue({ company });
    await act(async () => {
      root.render(createElement(AuthProvider, {
        initialSession: session("moderator"),
        children: createElement(CompanyModerationActions, { company })
      }));
    });

    const blockDetails = [...container.querySelectorAll("details")].find((details) => details.textContent?.includes("Блокировать"));
    const summary = blockDetails?.querySelector("summary");
    expect(summary).not.toBeNull();
    await act(async () => { summary!.dispatchEvent(new MouseEvent("click", { bubbles: true })); });

    const reason = blockDetails?.querySelector("textarea");
    expect(reason?.required).toBe(true);
    const confirm = [...(blockDetails?.querySelectorAll("button") || [])].find((button) => button.textContent?.includes("Подтвердить блокировку"));
    expect(confirm).not.toBeNull();
    await act(async () => { confirm!.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    expect(moderateCompany).not.toHaveBeenCalled();
    expect(container.querySelector('[role="alert"]')?.textContent).toBe("Укажите причину решения.");

    await act(async () => {
      const setValue = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
      setValue?.call(reason, "Нарушение правил пилота");
      reason!.dispatchEvent(new Event("input", { bubbles: true }));
      reason!.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await act(async () => { confirm!.dispatchEvent(new MouseEvent("click", { bubbles: true })); });

    expect(moderateCompany).toHaveBeenCalledWith(company.id, "block", company.revision, "Нарушение правил пилота");
  });

  it("shows company approval to admins while keeping reject and block for moderators", async () => {
    const renderForRole = async (role: User["role"]) => act(async () => {
      root.render(createElement(AuthProvider, {
        key: role,
        initialSession: session(role),
        children: createElement(CompanyModerationActions, { company })
      }));
    });

    await renderForRole("moderator");
    expect(container.querySelector("button")?.textContent).not.toContain("Допустить");
    expect(container.textContent).toContain("Отклонить");
    expect(container.textContent).toContain("Блокировать");

    await renderForRole("admin");
    expect(container.querySelector("button")?.textContent).toContain("Допустить");
    expect(container.textContent).toContain("Отклонить");
    expect(container.textContent).toContain("Блокировать");
  });
});

describe("listing moderation", () => {
  it("keeps approve, reject, and block for pending listings", async () => {
    await act(async () => { root.render(createElement(ListingModerationActions, { listing: listing("pending_review") })); });

    expect(container.querySelector('button')?.textContent).toContain("Одобрить");
    expect(container.textContent).toContain("Отклонить");
    expect(container.textContent).toContain("Заблокировать");
  });

  it("only offers a reasoned block for active listings", async () => {
    await act(async () => { root.render(createElement(ListingModerationActions, { listing: listing("active") })); });

    expect(container.textContent).not.toContain("Одобрить");
    expect(container.textContent).not.toContain("Отклонить");
    expect(container.textContent).toContain("Заблокировать");
    expect(container.querySelectorAll("details")).toHaveLength(1);
    expect(container.querySelector("textarea")?.required).toBe(true);
  });
});
