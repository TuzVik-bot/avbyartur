import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BillingOrderButton } from "@/components/billing-order-button";
import { api, ApiClientError } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, api: { ...actual.api, createBillingOrder: vi.fn() } };
});

const createOrder = vi.mocked(api.createBillingOrder);

const tariff = { id: "tariff-1", name: "Выделение на неделю", amount: "12.50", currency: "BYN", duration_days: 7 };

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  createOrder.mockReset();
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("billing order button", () => {
  it("keeps ordering closed while the payment provider is unconfigured", async () => {
    await act(async () => {
      root.render(createElement(BillingOrderButton, { tariff, listingId: "listing-1", companyId: null, ordersEnabled: false }));
    });
    const button = container.querySelector<HTMLButtonElement>("button")!;
    expect(button.textContent).toBe("Оформление закрыто");
    expect(button.disabled).toBe(true);
    expect(createOrder).not.toHaveBeenCalled();
  });

  it("requires a promotion target before enabling the button", async () => {
    await act(async () => {
      root.render(createElement(BillingOrderButton, { tariff, listingId: null, companyId: null, ordersEnabled: true }));
    });
    const button = container.querySelector<HTMLButtonElement>("button")!;
    expect(button.textContent).toBe("Выберите объект продвижения");
    expect(button.disabled).toBe(true);
  });

  it("creates the order and redirects to the provider checkout", async () => {
    const assign = vi.fn();
    Object.defineProperty(window, "location", { value: { ...window.location, assign }, writable: true });
    createOrder.mockResolvedValue({ order: { id: "order-1" } as never, checkout_url: "https://checkout.example.test/pay?order=order-1" });
    await act(async () => {
      root.render(createElement(BillingOrderButton, { tariff, listingId: "listing-1", companyId: null, ordersEnabled: true }));
    });
    const button = container.querySelector<HTMLButtonElement>("button")!;
    expect(button.textContent).toBe("Оформить");
    await act(async () => { button.click(); });
    expect(createOrder).toHaveBeenCalledWith({ tariff_id: "tariff-1", listing_id: "listing-1", company_id: null }, expect.any(String));
    expect(assign).toHaveBeenCalledWith("https://checkout.example.test/pay?order=order-1");
  });

  it("explains an overlap conflict without redirecting", async () => {
    const assign = vi.fn();
    Object.defineProperty(window, "location", { value: { ...window.location, assign }, writable: true });
    createOrder.mockRejectedValue(new ApiClientError(409, { code: "promotion_overlap", message: "This service is already active or has a pending checkout" }));
    await act(async () => {
      root.render(createElement(BillingOrderButton, { tariff, listingId: "listing-1", companyId: null, ordersEnabled: true }));
    });
    const button = container.querySelector<HTMLButtonElement>("button")!;
    await act(async () => { button.click(); });
    expect(assign).not.toHaveBeenCalled();
    expect(container.textContent).toContain("Эта услуга уже активна или ожидает оплаты.");
  });
});
