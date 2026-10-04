import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CatalogRequestsPage from "@/app/admin/catalog-requests/page";

const mocks = vi.hoisted(() => ({ requireSession: vi.fn() }));

vi.mock("@/lib/server", () => ({ requireSession: mocks.requireSession }));
vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) =>
    <a href={href} {...props}>{children}</a>,
}));

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
  mocks.requireSession.mockReset().mockResolvedValue({ user: { id: "moderator-1", role: "moderator" } });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

describe("catalog request admin page", () => {
  it("allows moderators to open the review queue", async () => {
    const page = await CatalogRequestsPage();
    await act(async () => { root.render(page); });
    expect(mocks.requireSession).toHaveBeenCalledWith("/admin/catalog-requests");
    expect(container.textContent).toContain("Не найденные модификации");
    expect(container.textContent).not.toContain("Нет доступа");
  });

  it("denies ordinary users before mounting the review queue", async () => {
    mocks.requireSession.mockResolvedValueOnce({ user: { id: "user-1", role: "user" } });
    const page = await CatalogRequestsPage();
    await act(async () => { root.render(page); });
    expect(container.textContent).toContain("Нет доступа");
    expect(container.textContent).toContain("модераторам и администраторам");
  });
});
