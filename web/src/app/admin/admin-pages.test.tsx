import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AdminPage from "@/app/admin/page";
import AdminUsersPage from "@/app/admin/users/page";
import AdminAuditPage from "@/app/admin/audit/page";
import AdminCatalogPage from "@/app/admin/catalog/page";
import AdminSettingsPage from "@/app/admin/settings/page";
import { type AdminAuditItem, type AdminOperations, type AdminUser } from "@/lib/admin";
import { adminServerApi } from "@/lib/admin-server";

const mocks = vi.hoisted(() => ({ requireSession: vi.fn() }));

vi.mock("@/lib/server", () => ({ requireSession: mocks.requireSession }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a>
}));

const operations: AdminOperations = {
  users_by_status: { active: 12, blocked: 2 },
  listings_by_status: { active: 3, pending_review: 4 },
  jobs_by_status: { succeeded: 9 },
  capabilities: { sms_login_enabled: false, public_registration_enabled: true }
};

const user: AdminUser = {
  id: "user-2", email: "person@example.test", display_name: "Пользователь", role: "user", status: "active", created_at: "2026-10-01T08:00:00Z"
};

const audit: AdminAuditItem = {
  id: "audit-1", actor_id: "admin-1", entity_type: "user", entity_id: user.id,
  action: "admin_user_updated", details: { reason: "Проверка доступа", to_role: "moderator", password: "must not render" }, created_at: "2026-10-01T08:00:00Z"
};

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
  mocks.requireSession.mockReset().mockResolvedValue({ user: { id: "admin-1", role: "admin" } });
  vi.spyOn(adminServerApi, "operations").mockResolvedValue(operations);
  vi.spyOn(adminServerApi, "users").mockResolvedValue({ items: [user], total: 1, page: 1, page_size: 25 });
  vi.spyOn(adminServerApi, "audit").mockResolvedValue({ items: [audit], total: 1, page: 1, page_size: 25 });
  vi.spyOn(adminServerApi, "catalog").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
  vi.spyOn(adminServerApi, "settings").mockResolvedValue({ items: [] });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

async function render(element: React.ReactNode) {
  await act(async () => { root.render(element); });
}

describe("admin pages", () => {
  it("shows operations and capability summary to administrators", async () => {
    const page = await AdminPage();
    await render(page);

    expect(mocks.requireSession).toHaveBeenCalledWith("/admin");
    expect(adminServerApi.operations).toHaveBeenCalledOnce();
    expect(container.textContent).toContain("Пользователи");
    expect(container.textContent).toContain("12");
    expect(container.textContent).toContain("Публичная регистрация");
    expect(container.textContent).toContain("Выкл.");
  });

  it("does not load administration data for non-admin roles", async () => {
    mocks.requireSession.mockResolvedValueOnce({ user: { id: "mod-1", role: "moderator" } });
    const page = await AdminPage();
    await render(page);

    expect(container.textContent).toContain("Нет доступа");
    expect(adminServerApi.operations).not.toHaveBeenCalled();
  });

  it("applies directory filters before rendering the current user page", async () => {
    const page = await AdminUsersPage({ searchParams: Promise.resolve({ q: " person@example.test ", role: "user", status: "active", page: "2" }) });
    await render(page);

    expect(adminServerApi.users).toHaveBeenCalledWith({ page: 2, page_size: 25, q: "person@example.test", role: "user", status: "active" });
    expect(container.textContent).toContain("person@example.test");
    expect(container.querySelector('input[name="q"]')?.getAttribute("value")).toBe("person@example.test");
  });

  it("does not request users for a non-admin role", async () => {
    mocks.requireSession.mockResolvedValueOnce({ user: { id: "user-1", role: "user" } });
    const page = await AdminUsersPage({ searchParams: Promise.resolve({}) });
    await render(page);

    expect(container.textContent).toContain("Нет доступа");
    expect(adminServerApi.users).not.toHaveBeenCalled();
  });

  it("filters audit history and renders only the safe details supplied by the API", async () => {
    const page = await AdminAuditPage({ searchParams: Promise.resolve({ entity_type: "user", entity_id: user.id }) });
    await render(page);

    expect(adminServerApi.audit).toHaveBeenCalledWith({ page: 1, page_size: 25, entity_type: "user", entity_id: user.id });
    expect(container.textContent).toContain("admin_user_updated");
    expect(container.textContent).toContain("Проверка доступа");
    expect(container.textContent).not.toContain("must not render");
  });

  it("shows safe tariff values before and after an audited change", async () => {
    vi.mocked(adminServerApi.audit).mockResolvedValueOnce({ items: [{ ...audit, entity_type: "billing_tariff", action: "billing_tariff_updated", details: { reason: "Тариф утверждён владельцем", before: { code: "bump-week", service_code: "bump", name: "Поднять", amount: "12.34", currency: "BYN", duration_days: 7, listing_quota: null, status: "active" }, after: { code: "bump-week", service_code: "bump", name: "Поднять", amount: "25.67", currency: "BYN", duration_days: 30, listing_quota: null, status: "disabled" } } }], total: 1, page: 1, page_size: 25 });
    await render(await AdminAuditPage({ searchParams: Promise.resolve({ entity_type: "billing_tariff" }) }));
    expect(container.textContent).toContain("12.34");
    expect(container.textContent).toContain("25.67");
    expect(container.textContent).toContain("Тариф утверждён владельцем");
    expect(container.textContent).not.toContain("[object Object]");
  });

  it("encodes and applies catalog filters while preserving an explicit empty state", async () => {
    const page = await AdminCatalogPage({ searchParams: Promise.resolve({ kind: "models", q: "  Corolla ", page: "3" }) });
    await render(page);

    expect(adminServerApi.catalog).toHaveBeenCalledWith("models", { page: 3, page_size: 25, q: "Corolla" });
    expect(container.querySelector<HTMLSelectElement>('select[name="kind"]')?.value).toBe("models");
    expect(container.textContent).toContain("Записи не найдены");
  });

  it("does not fetch catalog or runtime settings for non-admin roles", async () => {
    mocks.requireSession.mockResolvedValueOnce({ user: { id: "user-1", role: "user" } });
    const catalogPage = await AdminCatalogPage({ searchParams: Promise.resolve({}) });
    await render(catalogPage);
    expect(container.textContent).toContain("Нет доступа");
    expect(adminServerApi.catalog).not.toHaveBeenCalled();

    mocks.requireSession.mockResolvedValueOnce({ user: { id: "user-1", role: "user" } });
    const settingsPage = await AdminSettingsPage();
    await render(settingsPage);
    expect(container.textContent).toContain("Нет доступа");
    expect(adminServerApi.settings).not.toHaveBeenCalled();
  });

  it("shows a clear empty state when no runtime limits have overrides", async () => {
    const page = await AdminSettingsPage();
    await render(page);
    expect(adminServerApi.settings).toHaveBeenCalledOnce();
    expect(container.textContent).toContain("Runtime-лимиты не настроены");
  });
});
