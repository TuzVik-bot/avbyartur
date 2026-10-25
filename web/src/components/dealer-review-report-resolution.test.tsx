import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DealerReviewReportResolution } from "@/components/moderation-actions";
import { api } from "@/lib/api";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const report = {
  id: "report-1", review_id: "review-1", company_name: "Dealer One", review_rating: 2,
  review_text: "Опубликованный отзыв", reason: "Прошу проверить", status: "open" as const,
  created_at: "2026-10-15T10:00:00Z"
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

it("submits a moderator resolution and refreshes the queue", async () => {
  const resolve = vi.spyOn(api, "resolveDealerReviewReport").mockResolvedValue({ report: { ...report, status: "resolved", resolution: "Решено" } });
  await act(async () => { root.render(createElement(DealerReviewReportResolution, { report })); });
  const input = container.querySelector<HTMLInputElement>('input[name="resolution"]')!;
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), "value")?.set;
  setter?.call(input, "Решено");
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
  await act(async () => {
    container.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await new Promise((done) => setTimeout(done, 0));
  });

  expect(resolve).toHaveBeenCalledWith("report-1", "Решено");
  expect(container.textContent).toContain("Жалоба закрыта");
});
