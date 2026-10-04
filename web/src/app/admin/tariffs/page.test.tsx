import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AdminTariffsPage from "@/app/admin/tariffs/page";
import type { AdminTariffPage } from "@/lib/admin-tariffs";
import { adminTariffsServerApi } from "@/lib/admin-tariffs-server";

const mocks = vi.hoisted(() => ({ requireSession: vi.fn(), refresh: vi.fn() }));

vi.mock("@/lib/server", () => ({ requireSession: mocks.requireSession }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: mocks.refresh }) }));
vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a>
}));

const tariffPage: AdminTariffPage = { items: [], total: 0, page: 1, page_size: 25 };
let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
  mocks.requireSession.mockReset().mockResolvedValue({ user: { id: "admin-1", role: "admin" } });
  vi.spyOn(adminTariffsServerApi, "list").mockResolvedValue(tariffPage);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

async function render(element: React.ReactNode) {
  await act(async () => { root.render(element); });
}

describe("admin tariffs page", () => {
  it("loads the owner-defined list and keeps checkout state explicit", async () => {
    const page = await AdminTariffsPage();
    await render(page);

    expect(mocks.requireSession).toHaveBeenCalledWith("/admin/tariffs");
    expect(adminTariffsServerApi.list).toHaveBeenCalledOnce();
    expect(container.textContent).toContain("Тарифов пока нет");
    expect(container.textContent).toContain("Платёжный checkout закрыт");
  });

  it("does not request tariff data for non-admin roles", async () => {
    mocks.requireSession.mockResolvedValueOnce({ user: { id: "user-1", role: "user" } });
    const page = await AdminTariffsPage();
    await render(page);

    expect(container.textContent).toContain("Нет доступа");
    expect(adminTariffsServerApi.list).not.toHaveBeenCalled();
  });

  it("shows a retryable error when the tariff list cannot be loaded", async () => {
    vi.spyOn(adminTariffsServerApi, "list").mockRejectedValueOnce(new Error("API unavailable"));
    const page = await AdminTariffsPage();
    await render(page);

    expect(container.querySelector('[role="alert"]')?.textContent).toContain("Не удалось загрузить тарифы");
  });
});
