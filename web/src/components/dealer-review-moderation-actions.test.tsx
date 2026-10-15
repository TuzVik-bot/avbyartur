import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DealerReviewModerationActions } from "@/components/moderation-actions";
import { api } from "@/lib/api";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const review = {
  id: "review-1", rating: 2, text: "Отзыв", created_at: "2026-10-15T10:00:00Z",
  status: "pending" as const, revision: 4, moderation_reason: null, company_id: "company-1", author_id: "author-1"
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

describe("dealer review moderation actions", () => {
  it.each(["published", "rejected"] as const)("sends the revision and rationale when setting %s", async (status) => {
    const moderate = vi.spyOn(api, "moderateDealerReview").mockResolvedValue({ review: { ...review, status, revision: 5 } });
    await act(async () => { root.render(createElement(DealerReviewModerationActions, { review })); });
    const textarea = container.querySelector<HTMLTextAreaElement>("textarea")!;
    const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(textarea), "value")?.set;
    setter?.call(textarea, "Решение проверено");
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
    textarea.dispatchEvent(new Event("change", { bubbles: true }));
    const button = [...container.querySelectorAll("button")].find((item) => item.textContent?.includes(status === "published" ? "Опубликовать" : "Отклонить"))!;
    await act(async () => { button.click(); await new Promise((done) => setTimeout(done, 0)); });

    expect(moderate).toHaveBeenCalledWith("review-1", 4, status, "Решение проверено");
  });
});
