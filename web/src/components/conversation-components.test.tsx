import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ConversationInbox } from "@/components/conversation-inbox";
import { ConversationStartForm } from "@/components/conversation-start-form";
import { ConversationThreadView } from "@/components/conversation-thread";
import { api } from "@/lib/api";
import { MAX_CONVERSATION_MESSAGE_LENGTH, type ConversationMessage, type ConversationSummary, type ConversationThread } from "@/lib/types";

const mocks = vi.hoisted(() => ({
  router: { push: vi.fn(), replace: vi.fn(), refresh: vi.fn() },
  user: { id: "buyer-1", display_name: "Покупатель", email: "buyer@example.test", role: "user" as const, company_id: null }
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a>
}));
vi.mock("next/navigation", () => ({ useRouter: () => mocks.router }));
vi.mock("@/components/auth-provider", () => ({ useAuth: () => ({ user: mocks.user }) }));

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
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

const summary: ConversationSummary = {
  id: "conversation-1",
  listing: { id: "listing-1", title: "BMW 320d", slug: "bmw-320d" },
  buyer_id: "buyer-1",
  seller_id: "seller-1",
  participants: [{ id: "buyer-1", display_name: "Покупатель" }, { id: "seller-1", display_name: "Продавец" }],
  last_message: { id: "message-1", body: "Есть история обслуживания: https://example.test", sender_id: "seller-1", created_at: "2026-09-30T10:00:00Z", read_at: null },
  last_message_at: "2026-09-30T10:00:00Z",
  unread_count: 2,
  blocked_by_me: false,
  is_blocked: false
};

const firstMessage: ConversationMessage = {
  id: "message-1",
  conversation_id: summary.id,
  sender_id: "seller-1",
  body: "Привет! <img src=x onerror=alert(1)> https://example.test",
  created_at: "2026-09-30T10:00:00Z",
  read_at: null
};

const thread: ConversationThread = { conversation: summary, messages: [firstMessage], has_more: false, next_before_sequence: null };

describe("ConversationInbox", () => {
  it("projects the other participant and plain-text preview from the API response", async () => {
    const load = vi.spyOn(api, "conversations").mockResolvedValue({ items: [summary] });
    await act(async () => { root.render(createElement(ConversationInbox)); });

    expect(load).toHaveBeenCalledOnce();
    expect(container.textContent).toContain("Продавец");
    expect(container.textContent).toContain("BMW 320d");
    expect(container.textContent).toContain("https://example.test");
    expect(container.querySelector(".conversation-preview a")).toBeNull();
    expect(container.querySelector('[aria-label="Непрочитанных сообщений: 2"]')).not.toBeNull();
    expect(container.querySelector('a[href="/account/messages/conversation-1"]')).not.toBeNull();
    expect(container.textContent).toContain("Не переводите предоплату");
  });

  it("shows a retry state after a failed load and keeps it distinct from an empty inbox", async () => {
    const load = vi.spyOn(api, "conversations").mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({ items: [] });
    await act(async () => { root.render(createElement(ConversationInbox)); });

    expect(container.textContent).toContain("Не удалось загрузить переписки");
    expect(container.textContent).not.toContain("Пока нет переписок");
    const retry = [...container.querySelectorAll("button")].find((button) => button.textContent?.includes("Повторить"));
    await act(async () => { retry?.click(); });

    expect(load).toHaveBeenCalledTimes(2);
    expect(container.textContent).toContain("Пока нет переписок");
  });

  it("redirects to login with the inbox path after the session expires", async () => {
    const { ApiClientError } = await import("@/lib/api");
    vi.spyOn(api, "conversations").mockRejectedValue(new ApiClientError(401, { message: "Unauthorized" }));
    await act(async () => { root.render(createElement(ConversationInbox)); });

    expect(mocks.router.replace).toHaveBeenCalledWith("/login?next=%2Faccount%2Fmessages");
  });
});

describe("ConversationThreadView", () => {
  it("loads an older cursor page and prepends it without changing read state", async () => {
    const olderMessage: ConversationMessage = {
      ...firstMessage,
      id: "message-0",
      body: "Более раннее сообщение",
      created_at: "2026-09-30T09:55:00Z"
    };
    const latestPage: ConversationThread = { ...thread, has_more: true, next_before_sequence: 2 };
    const olderPage: ConversationThread = { ...thread, messages: [olderMessage], has_more: false, next_before_sequence: null };
    const load = vi.spyOn(api, "conversation").mockResolvedValueOnce(latestPage).mockResolvedValueOnce(olderPage);
    const markRead = vi.spyOn(api, "markConversationRead").mockResolvedValue({ ok: true });

    await act(async () => { root.render(createElement(ConversationThreadView, { conversationId: summary.id })); });

    const loadOlder = [...container.querySelectorAll("button")].find((button) => button.textContent?.includes("Загрузить более ранние сообщения"));
    expect(loadOlder).toBeDefined();
    await act(async () => { loadOlder?.click(); });

    expect(load).toHaveBeenNthCalledWith(1, summary.id);
    expect(load).toHaveBeenNthCalledWith(2, summary.id, { beforeSequence: 2 });
    expect(markRead).toHaveBeenCalledOnce();
    expect([...container.querySelectorAll(".conversation-message-body")].map((item) => item.textContent)).toEqual([
      "Более раннее сообщение",
      firstMessage.body
    ]);
    expect(container.querySelector(".conversation-thread-history-error")).toBeNull();
    expect([...container.querySelectorAll("button")].some((button) => button.textContent?.includes("Загрузить более ранние сообщения"))).toBe(false);
  });

  it("marks loaded messages read, displays plain text, and sends the typed message", async () => {
    const load = vi.spyOn(api, "conversation").mockResolvedValue(thread);
    const markRead = vi.spyOn(api, "markConversationRead").mockResolvedValue({ ok: true });
    const sent: ConversationMessage = { ...firstMessage, id: "message-2", sender_id: "buyer-1", body: "Здравствуйте, можно осмотреть?", created_at: "2026-09-30T10:05:00Z" };
    const send = vi.spyOn(api, "sendConversationMessage").mockRejectedValueOnce(new Error("offline")).mockResolvedValue({ message: sent });
    await act(async () => { root.render(createElement(ConversationThreadView, { conversationId: summary.id })); });

    expect(load).toHaveBeenCalledWith(summary.id);
    expect(markRead).toHaveBeenCalledWith(summary.id, expect.any(String));
    expect(container.textContent).toContain("Продавец");
    expect(container.querySelector(".conversation-message-body img")).toBeNull();
    expect(container.querySelector(".conversation-message-body a")).toBeNull();
    expect(container.querySelector('[role="log"][aria-label="Сообщения в переписке"][aria-live="polite"]')).not.toBeNull();
    expect(container.textContent).toContain("Не переводите предоплату");

    const textarea = container.querySelector<HTMLTextAreaElement>('textarea[name="message"]')!;
    expect(textarea.maxLength).toBe(2000);
    expect(container.textContent).toContain("0/2000 символов");
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!;
      setter.call(textarea, "Здравствуйте, можно осмотреть?");
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });
    const form = textarea.closest("form")!;
    await act(async () => {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await Promise.resolve();
    });

    expect(container.textContent).toContain("offline");
    const firstKey = send.mock.calls[0]?.[2];
    await act(async () => {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await Promise.resolve();
    });

    expect(send).toHaveBeenCalledTimes(2);
    expect(send.mock.calls[0]).toEqual([summary.id, "Здравствуйте, можно осмотреть?", expect.any(String)]);
    expect(send.mock.calls[1]?.[2]).toBe(firstKey);
    expect(container.textContent).toContain("Здравствуйте, можно осмотреть?");

    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!;
      setter.call(textarea, "x".repeat(MAX_CONVERSATION_MESSAGE_LENGTH + 1));
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(container.textContent).toContain("2001/2000 символов");
    expect(form.querySelector<HTMLButtonElement>('button[type="submit"]')?.disabled).toBe(true);
    await act(async () => { form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("не должно превышать 2000");
  });

  it("retries a failed read action with the same key and uses a fresh key for a later message", async () => {
    vi.spyOn(api, "conversation").mockResolvedValue(thread);
    const markRead = vi.spyOn(api, "markConversationRead").mockRejectedValueOnce(new Error("offline")).mockResolvedValue({ ok: true });
    const sentOne: ConversationMessage = { ...firstMessage, id: "message-2", sender_id: "buyer-1", body: "Первое сообщение", created_at: "2026-09-30T10:05:00Z" };
    const sentTwo: ConversationMessage = { ...sentOne, id: "message-3", body: "Второе сообщение", created_at: "2026-09-30T10:06:00Z" };
    const send = vi.spyOn(api, "sendConversationMessage").mockResolvedValueOnce({ message: sentOne }).mockResolvedValueOnce({ message: sentTwo });
    await act(async () => { root.render(createElement(ConversationThreadView, { conversationId: summary.id })); });

    expect(container.textContent).toContain("offline");
    const retryRead = [...container.querySelectorAll("button")].find((button) => button.textContent?.includes("Повторить отметку о прочтении"));
    await act(async () => { retryRead?.click(); });
    expect(markRead).toHaveBeenCalledTimes(2);
    expect(markRead.mock.calls[1]?.[1]).toBe(markRead.mock.calls[0]?.[1]);

    const textarea = container.querySelector<HTMLTextAreaElement>('textarea[name="message"]')!;
    const form = textarea.closest("form")!;
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!;
    await act(async () => {
      setter.call(textarea, "Первое сообщение");
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => { form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); await Promise.resolve(); });
    const firstKey = send.mock.calls[0]?.[2];

    await act(async () => {
      setter.call(textarea, "Второе сообщение");
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => { form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); await Promise.resolve(); });

    expect(send).toHaveBeenCalledTimes(2);
    expect(firstKey).toEqual(expect.any(String));
    expect(send.mock.calls[1]?.[2]).toEqual(expect.any(String));
    expect(send.mock.calls[1]?.[2]).not.toBe(firstKey);
  });

  it("confirms a block action and disables sending once blocked", async () => {
    vi.spyOn(api, "conversation").mockResolvedValue(thread);
    vi.spyOn(api, "markConversationRead").mockResolvedValue({ ok: true });
    const block = vi.spyOn(api, "blockConversation").mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({ ok: true });
    await act(async () => { root.render(createElement(ConversationThreadView, { conversationId: summary.id })); });

    const blockButton = [...container.querySelectorAll("button")].find((button) => button.textContent?.includes("Заблокировать"));
    await act(async () => { blockButton?.click(); });
    expect(container.querySelector('[aria-label="Подтверждение блокировки"]')).not.toBeNull();
    const confirm = [...container.querySelectorAll("button")].find((button) => button.textContent === "Заблокировать");
    await act(async () => { confirm?.click(); });
    expect(container.textContent).toContain("offline");
    const retry = [...container.querySelectorAll("button")].find((button) => button.textContent === "Заблокировать");
    await act(async () => { retry?.click(); });

    expect(block).toHaveBeenCalledTimes(2);
    expect(block.mock.calls[0]).toEqual([summary.id, expect.any(String)]);
    expect(block.mock.calls[1]?.[1]).toBe(block.mock.calls[0]?.[1]);
    expect(container.textContent).toContain("Вы заблокировали эту переписку");
    expect(container.querySelector('textarea[name="message"]')).toBeNull();
  });

  it("shows load errors with a retry instead of rendering an empty thread", async () => {
    vi.spyOn(api, "conversation").mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(thread);
    vi.spyOn(api, "markConversationRead").mockResolvedValue({ ok: true });
    await act(async () => { root.render(createElement(ConversationThreadView, { conversationId: summary.id })); });

    expect(container.textContent).toContain("Не удалось загрузить переписку");
    expect(container.textContent).not.toContain("В этой переписке пока нет сообщений");
    const retry = [...container.querySelectorAll("button")].find((button) => button.textContent?.includes("Повторить"));
    await act(async () => { retry?.click(); });
    expect(container.textContent).toContain("BMW 320d");
  });
});

describe("ConversationStartForm", () => {
  it("creates a plain-text conversation and opens its thread", async () => {
    const create = vi.spyOn(api, "createConversation").mockRejectedValueOnce(new Error("offline")).mockResolvedValue({ conversation: summary });
    await act(async () => { root.render(createElement(ConversationStartForm, { listingId: "listing-1", listingTitle: "BMW 320d" })); });

    const textarea = container.querySelector<HTMLTextAreaElement>('textarea[name="message"]')!;
    expect(textarea.maxLength).toBe(2000);
    expect(container.textContent).toContain("0/2000 символов");
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!;
      setter.call(textarea, "Здравствуйте!");
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });
    const form = textarea.closest("form")!;
    await act(async () => {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await Promise.resolve();
    });
    expect(container.textContent).toContain("offline");
    await act(async () => {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await Promise.resolve();
    });

    expect(create).toHaveBeenCalledTimes(2);
    expect(create.mock.calls[0]).toEqual(["listing-1", "Здравствуйте!", expect.any(String)]);
    expect(create.mock.calls[1]?.[2]).toBe(create.mock.calls[0]?.[2]);
    expect(mocks.router.replace).toHaveBeenCalledWith("/account/messages/conversation-1");

    await act(async () => { form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); await Promise.resolve(); });
    expect(create).toHaveBeenCalledTimes(3);
    expect(create.mock.calls[2]?.[2]).toEqual(expect.any(String));
    expect(create.mock.calls[2]?.[2]).not.toBe(create.mock.calls[1]?.[2]);

    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!;
      setter.call(textarea, "x".repeat(MAX_CONVERSATION_MESSAGE_LENGTH + 1));
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(container.textContent).toContain("2001/2000 символов");
    expect(form.querySelector<HTMLButtonElement>('button[type="submit"]')?.disabled).toBe(true);
    await act(async () => { form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })); });
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("не должно превышать 2000");
  });
});
