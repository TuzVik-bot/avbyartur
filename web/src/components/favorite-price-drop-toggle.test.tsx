import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { FavoritePriceDropToggle } from "@/components/favorite-price-drop-toggle";
import { api } from "@/lib/api";

const routerMocks = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => routerMocks }));

let container: HTMLDivElement;
let root: Root;
let setAlert: Mock<typeof api.setFavoritePriceDropAlert>;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  routerMocks.push.mockReset();
  setAlert = vi.spyOn(api, "setFavoritePriceDropAlert");
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

async function render(initialEnabled = false) {
  await act(async () => root.render(createElement(FavoritePriceDropToggle, {
    listingId: "listing-1",
    listingTitle: "Марка Модель",
    initialEnabled
  })));
}

describe("FavoritePriceDropToggle", () => {
  it("starts opt-in off and labels the setting for the exact listing", async () => {
    await render();

    const checkbox = container.querySelector<HTMLInputElement>('input[type="checkbox"]');
    expect(checkbox?.checked).toBe(false);
    expect(checkbox?.getAttribute("aria-label")).toBe("Уведомлять о снижении цены: Марка Модель");
    expect(setAlert).not.toHaveBeenCalled();
  });

  it("requires an explicit enable and supports turning the alert back off", async () => {
    setAlert.mockResolvedValueOnce({ enabled: true }).mockResolvedValueOnce({ enabled: false });
    await render();

    const checkbox = container.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
    await act(async () => { checkbox.click(); await Promise.resolve(); });
    expect(setAlert).toHaveBeenNthCalledWith(1, "listing-1", true);
    expect(checkbox.checked).toBe(true);
    expect(container.textContent).toContain("Уведомления о снижении цены включены.");

    await act(async () => { checkbox.click(); await Promise.resolve(); });
    expect(setAlert).toHaveBeenNthCalledWith(2, "listing-1", false);
    expect(checkbox.checked).toBe(false);
    expect(container.textContent).toContain("Уведомления о снижении цены выключены.");
  });

  it("keeps the saved choice unchanged and explains a failed update", async () => {
    setAlert.mockRejectedValueOnce(new Error("offline"));
    await render();

    const checkbox = container.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
    await act(async () => { checkbox.click(); await Promise.resolve(); });

    expect(checkbox.checked).toBe(false);
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("Не удалось сохранить настройку уведомления");
  });
});
