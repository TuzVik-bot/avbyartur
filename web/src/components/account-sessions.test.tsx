import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "@/components/auth-provider";
import { AccountSessions, type AccountSession, type AccountSessionList } from "@/components/account-sessions";
import * as api from "@/lib/api";

const mocks = vi.hoisted(() => ({
  replace: vi.fn(),
  refresh: vi.fn()
}));

vi.mock("next/navigation", () => ({ useRouter: () => mocks }));

const current: AccountSession = {
  id: "session-current",
  created_at: "2026-09-30T10:00:00Z",
  is_current: true
};

const other: AccountSession = {
  id: "session-other",
  created_at: "2026-09-29T08:30:00Z",
  is_current: false
};

const authSession = {
  csrf_token: "csrf-for-test",
  user: {
    id: "user-1",
    email: "sessions@example.test",
    display_name: "Тест",
    role: "user" as const,
    company_id: null
  }
};

let container: HTMLDivElement;
let root: Root;

function buttonWith(text: string) {
  return [...container.querySelectorAll("button")].find((button) => button.textContent?.includes(text));
}

async function render(initialSessions: AccountSession[] | null) {
  await act(async () => {
    root.render(createElement(
      AuthProvider,
      { initialSession: authSession, children: createElement(AccountSessions, { initialSessions }) }
    ));
  });
}

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

describe("AccountSessions", () => {
  it("lists the current session and revokes only a selected other session", async () => {
    const request = vi.spyOn(api, "apiRequest").mockResolvedValue({ ok: true } as never);
    await render([current, other]);

    expect(container.textContent).toContain("Этот сеанс");
    expect(container.textContent).toContain("Текущий");
    expect(container.textContent).toContain("Другой сеанс");
    expect(container.querySelectorAll('ul[aria-label="Список активных сеансов"] > li')).toHaveLength(2);
    const accessibleNames = [...container.querySelectorAll(".account-list-item button")]
      .map((button) => button.getAttribute("aria-label"));
    expect(new Set(accessibleNames).size).toBe(2);
    expect(accessibleNames[0]).toContain("текущий сеанс №1");
    expect(accessibleNames[1]).toContain("другой сеанс №2");
    const otherCard = [...container.querySelectorAll<HTMLElement>(".account-list-item")]
      .find((card) => card.textContent?.includes("Другой сеанс"));
    const revokeButton = otherCard?.querySelector("button");
    await act(async () => { revokeButton?.click(); });

    expect(request).toHaveBeenCalledWith("me/sessions/session-other", { method: "DELETE" });
    expect(container.textContent).not.toContain("Другой сеанс");
    expect(container.textContent).toContain("Сеанс завершён.");
  });

  it("keeps the current session after revoking the others", async () => {
    const request = vi.spyOn(api, "apiRequest").mockResolvedValue({ revoked_count: 2 } as never);
    await render([current, other]);

    await act(async () => { buttonWith("Завершить остальные")?.click(); });

    expect(request).toHaveBeenCalledWith("me/sessions/revoke-others", { method: "POST", body: "{}" });
    expect(container.textContent).toContain("Этот сеанс");
    expect(container.textContent).not.toContain("Другой сеанс");
    expect(container.textContent).toContain("Остальные сеансы завершены.");
  });

  it("clears local auth and redirects after ending the current session", async () => {
    const request = vi.spyOn(api, "apiRequest").mockResolvedValue({ ok: true } as never);
    await render([current]);

    await act(async () => { buttonWith("Завершить этот сеанс")?.click(); });

    expect(request).toHaveBeenCalledWith("me/sessions/session-current", { method: "DELETE" });
    expect(mocks.replace).toHaveBeenCalledWith("/login?next=%2Faccount%2Fsettings");
    expect(mocks.refresh).toHaveBeenCalled();
  });

  it("offers retry after load failure and shows action errors", async () => {
    const request = vi.spyOn(api, "apiRequest")
      .mockResolvedValueOnce({ items: [current] } as unknown as AccountSessionList)
      .mockRejectedValueOnce(new Error("Не удалось выполнить запрос"));
    await render(null);
    expect(container.textContent).toContain("Не удалось загрузить активные сеансы.");

    await act(async () => { buttonWith("Повторить")?.click(); });
    expect(container.textContent).toContain("Этот сеанс");

    await act(async () => { buttonWith("Завершить этот сеанс")?.click(); });
    expect(container.textContent).toContain("Не удалось выполнить запрос");
    expect(request).toHaveBeenCalledTimes(2);
  });
});
