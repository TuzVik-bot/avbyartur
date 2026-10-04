import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/lib/api";
import { dealerTeamApi, type DealerTeamMember } from "@/lib/dealer";
import { DealerTeam } from "@/components/dealer-team";

const owner: DealerTeamMember = {
  id: "owner-row", user_id: "owner-user", email: "owner@example.test", display_name: "Владелец",
  role: "owner", status: "active", revision: 2, created_at: "2026-10-01T10:00:00Z"
};
const seller: DealerTeamMember = {
  id: "seller-row", user_id: "seller-user", email: "seller@example.test", display_name: "Продавец",
  role: "seller", status: "active", revision: 6, created_at: "2026-10-01T10:00:00Z"
};
const admin: DealerTeamMember = {
  ...seller, id: "admin-row", user_id: "admin-user", display_name: "Администратор", role: "admin"
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

async function render(members: DealerTeamMember[], currentUserId: string) {
  await act(async () => { root.render(createElement(DealerTeam, { initialMembers: members, currentUserId })); });
}

function changeValue(element: HTMLInputElement | HTMLSelectElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(element), "value")?.set;
  setter?.call(element, value);
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
}

describe("dealer team controls", () => {
  it("lets the owner invite an existing UUID and includes an admin role only for the owner", async () => {
    await render([owner, seller], owner.user_id);
    const add = vi.spyOn(dealerTeamApi, "add").mockResolvedValue({ member: { ...seller, id: "new-row", role: "admin" } });
    const form = container.querySelector<HTMLFormElement>(".dealer-team-add")!;
    const input = form.querySelector<HTMLInputElement>("input")!;
    const role = form.querySelector<HTMLSelectElement>("select")!;
    await act(async () => {
      changeValue(input, "3b241101-e2bb-4255-8caf-4136c566a962");
      changeValue(role, "admin");
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await Promise.resolve();
    });
    expect(add).toHaveBeenCalledWith("3b241101-e2bb-4255-8caf-4136c566a962", "admin", expect.any(String));
    expect(container.textContent).toContain("Пользователь добавлен в команду.");
  });

  it("prevents an admin from granting the admin role or managing another admin", async () => {
    await render([{ ...owner, role: "admin", user_id: "manager-user" }, admin, seller], "manager-user");
    const selects = [...container.querySelectorAll<HTMLSelectElement>("select")];
    expect(selects).toHaveLength(2);
    expect([...selects[0].options].some((option) => option.value === "admin")).toBe(false);
    expect([...selects[1].options].some((option) => option.value === "admin")).toBe(false);
    const adminRow = [...container.querySelectorAll("tbody tr")].find((row) => row.textContent?.includes("Администратор"))!;
    expect(adminRow.textContent).toContain("Управление недоступно");
    expect(adminRow.querySelectorAll("button")).toHaveLength(0);
  });

  it("sends the member's current revision and surfaces a stale-revision conflict", async () => {
    await render([owner, seller], owner.user_id);
    const update = vi.spyOn(dealerTeamApi, "update").mockRejectedValue(new ApiClientError(409, { code: "revision_conflict" }));
    const sellerRow = [...container.querySelectorAll("tbody tr")].find((row) => row.textContent?.includes("Продавец"))!;
    const role = sellerRow.querySelector<HTMLSelectElement>("select")!;
    await act(async () => { changeValue(role, "viewer"); });
    const save = [...sellerRow.querySelectorAll("button")].find((button) => button.textContent?.includes("Сохранить роль"));
    await act(async () => {
      save?.click();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(update).toHaveBeenCalledWith(seller, { role: "viewer" });
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("изменился");
  });

  it("keeps the team read-only for a seller", async () => {
    await render([owner, seller], seller.user_id);
    expect(container.querySelector(".dealer-team-add")).toBeNull();
    expect(container.querySelectorAll("tbody select")).toHaveLength(0);
    expect(container.textContent).toContain("может владелец или администратор");
  });
});
