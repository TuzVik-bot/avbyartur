import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DealerReviews } from "@/components/dealer-reviews";
import { api } from "@/lib/api";
import type { User } from "@/lib/types";

const authMocks = vi.hoisted(() => ({ user: null as User | null }));
vi.mock("@/components/auth-provider", () => ({ useAuth: () => ({ user: authMocks.user }) }));
vi.mock("next/link", () => ({ default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a> }));

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  authMocks.user = null;
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

const emptyReviews = { items: [], count: 0, average_rating: null };

describe("DealerReviews", () => {
  it("keeps the empty state unrated and explains the limit of reviews", async () => {
    await act(async () => { root.render(createElement(DealerReviews, { slug: "dealer", reviews: emptyReviews })); });
    expect(container.textContent).toContain("Отзывов пока нет");
    expect(container.textContent).toContain("Факт покупки не подтверждается");
    expect(container.querySelector(".rating")).toBeNull();
    expect(container.querySelector('a[href^="/login?"]')?.textContent).toContain("Войдите");
  });

  it("submits an authenticated review and presents its moderation status", async () => {
    authMocks.user = { id: "user-1", email: "user@example.test", display_name: "Пользователь", role: "user", status: "active", company_id: null, company_role: null } as User;
    vi.spyOn(api, "myDealerReview").mockResolvedValue({ review: null });
    const create = vi.spyOn(api, "createDealerReview").mockResolvedValue({ review: { id: "review-1", rating: 5, text: "Понравилось обслуживание", created_at: "2026-10-10T00:00:00Z", status: "pending", revision: 1, moderation_reason: null } });
    await act(async () => { root.render(createElement(DealerReviews, { slug: "dealer", reviews: emptyReviews })); await Promise.resolve(); });
    const text = container.querySelector("textarea")!;
    const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(text), "value")?.set;
    await act(async () => {
      setter?.call(text, "Понравилось обслуживание");
      text.dispatchEvent(new Event("input", { bubbles: true }));
      container.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await Promise.resolve();
    });
    expect(create).toHaveBeenCalledWith("dealer", { rating: 5, text: "Понравилось обслуживание" });
    expect(container.textContent).toContain("Статус: На проверке");
    expect(container.textContent).toContain("Отзыв отправлен на проверку модератору.");
  });
});
