import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ConversationStartForm } from "@/components/conversation-start-form";
import { api, ApiClientError } from "@/lib/api";

const mocks = vi.hoisted(() => ({
  router: { push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a>
}));
vi.mock("next/navigation", () => ({ useRouter: () => mocks.router }));

const DRAFT_KEY = "conversation-draft:listing-1";
let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  window.sessionStorage.clear();
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
  vi.clearAllMocks();
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

async function render(exchange = false) {
  await act(async () => root.render(createElement(ConversationStartForm, { listingId: "listing-1", listingTitle: "BMW 320d", exchange })));
  return container.querySelector<HTMLTextAreaElement>('textarea[name="message"]')!;
}

async function type(textarea: HTMLTextAreaElement, value: string) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(textarea, value);
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

async function submit(textarea: HTMLTextAreaElement) {
  await act(async () => { textarea.closest("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });
}

describe("ConversationStartForm draft and templates", () => {
  it("saves the typed message before sending a signed-out user to login and restores it on return", async () => {
    vi.spyOn(api, "createConversation").mockRejectedValue(new ApiClientError(401, { message: "Unauthorized" }));
    const textarea = await render();
    await type(textarea, "Добрый день! Когда можно посмотреть?");

    await submit(textarea);

    expect(window.sessionStorage.getItem(DRAFT_KEY)).toBe("Добрый день! Когда можно посмотреть?");
    expect(mocks.router.replace).toHaveBeenCalledWith(`/login?next=${encodeURIComponent("/account/messages/new?listing_id=listing-1")}`);

    act(() => root.unmount());
    act(() => { root = createRoot(container); });
    const restored = await render(true);
    expect(restored.value).toBe("Добрый день! Когда можно посмотреть?");
  });

  it("clears the saved draft once the conversation is created", async () => {
    window.sessionStorage.setItem(DRAFT_KEY, "Сохранённый текст");
    vi.spyOn(api, "createConversation").mockResolvedValue({ conversation: { id: "conversation-1" } } as Awaited<ReturnType<typeof api.createConversation>>);
    const textarea = await render();
    expect(textarea.value).toBe("Сохранённый текст");

    await submit(textarea);

    expect(window.sessionStorage.getItem(DRAFT_KEY)).toBeNull();
    expect(mocks.router.replace).toHaveBeenCalledWith("/account/messages/conversation-1");
  });

  it("inserts quick template questions into the message", async () => {
    const textarea = await render();
    const chips = [...container.querySelectorAll<HTMLButtonElement>("[data-message-template]")];
    expect(chips.map((chip) => chip.textContent)).toEqual(["Ещё продаётся?", "Возможен торг?", "Рассматриваете обмен?"]);
    expect(chips.every((chip) => chip.type === "button")).toBe(true);

    await act(async () => { chips[0]!.click(); });
    expect(textarea.value).toBe("Ещё продаётся?");
    await act(async () => { chips[1]!.click(); });
    expect(textarea.value).toBe("Ещё продаётся? Возможен торг?");
  });

  it("shows a Russian fallback instead of a raw technical error", async () => {
    vi.spyOn(api, "createConversation").mockRejectedValue(new Error("Failed to fetch"));
    const textarea = await render();
    await type(textarea, "Здравствуйте!");

    await submit(textarea);

    expect(container.querySelector('[role="alert"]')?.textContent).toBe("Не удалось начать переписку. Повторите попытку.");
  });

  it("keeps working when session storage is unavailable", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("denied"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("denied"); });
    vi.spyOn(api, "createConversation").mockRejectedValue(new ApiClientError(401, { message: "Unauthorized" }));
    const textarea = await render();
    await type(textarea, "Здравствуйте!");

    await submit(textarea);

    expect(mocks.router.replace).toHaveBeenCalledOnce();
  });
});
