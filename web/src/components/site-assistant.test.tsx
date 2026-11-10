import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SiteAssistant } from "./site-assistant";

vi.mock("next/navigation", () => ({ usePathname: () => "/" }));

const STORAGE_KEY = "avtorynok-assistant-chat";
const reply = (text: string, extra: Record<string, unknown> = {}) => ({ text, filters: { currency: "USD" }, labels: [], listings: [], links: [], engine: "ai", ...extra });
type PostBody = { message: string; history: { role: string; content: string }[] };

let root: Root;
let host: HTMLDivElement;
let posts: PostBody[];

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  Element.prototype.scrollIntoView = vi.fn();
  sessionStorage.clear();
  posts = [];
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
});

// Routes GET to the engine probe and hands each POST to the next queued responder.
function stubFetch(responders: (() => Response | Promise<Response>)[]) {
  vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) => {
    if (init?.method !== "POST") return Response.json({ engine: "ai" });
    posts.push(JSON.parse(String(init.body)));
    const next = responders.shift();
    if (!next) throw new Error("unexpected POST");
    return next();
  }));
}
const flush = () => act(async () => { for (let index = 0; index < 5; index++) await Promise.resolve(); await new Promise((resolve) => setTimeout(resolve, 0)); });
async function openPanel() {
  act(() => root.render(<SiteAssistant />));
  await act(async () => host.querySelector<HTMLButtonElement>("button[aria-controls='site-assistant']")!.click());
  await flush();
}
function textarea() { return host.querySelector("textarea")!; }
async function sendMessage(text: string) {
  const field = textarea();
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(field, text);
    field.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => host.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })));
  await flush();
}
const userBubbles = () => [...host.querySelectorAll("[role='log'] p")].filter((node) => node.textContent === "Автомат до 10 тысяч долларов");

describe("site assistant widget", () => {
  it("is a modal dialog and keeps the textarea focusable but read-only while waiting", async () => {
    let release: (value: Response) => void = () => {};
    stubFetch([() => new Promise<Response>((resolve) => { release = resolve; })]);
    await openPanel();
    expect(host.querySelector("[role='dialog']")?.getAttribute("aria-modal")).toBe("true");
    await sendMessage("Автомат до 10 тысяч долларов");
    expect(textarea().readOnly).toBe(true);
    expect(textarea().disabled).toBe(false);
    await act(async () => release(Response.json(reply("Нашёл варианты."))));
    await flush();
    expect(textarea().readOnly).toBe(false);
  });
  it("announces only the latest answer and shows the basic-mode notice", async () => {
    stubFetch([() => Response.json(reply("Ответ в базовом режиме.", { engine: "basic", notice: "Отвечаю в упрощённом режиме" }))]);
    await openPanel();
    await sendMessage("Автомат до 10 тысяч долларов");
    const live = host.querySelector("[aria-live='polite']");
    expect(live?.textContent).toBe("Ответ в базовом режиме.");
    expect(host.querySelector("[role='log']")?.getAttribute("aria-live")).toBe("off");
    expect(host.textContent).toContain("Отвечаю в упрощённом режиме");
  });
  it("shows a friendly error for a non-JSON gateway page", async () => {
    stubFetch([() => new Response("<html>502 Bad Gateway</html>", { status: 502, headers: { "Content-Type": "text/html" } })]);
    await openPanel();
    await sendMessage("Автомат до 10 тысяч долларов");
    expect(host.querySelector("[role='alert']")?.textContent).toContain("Помощник временно недоступен. Попробуйте позже.");
  });
  it("does not duplicate the user message in history or the thread when retrying", async () => {
    stubFetch([() => new Response("oops", { status: 502 }), () => Response.json(reply("Нашёл варианты."))]);
    await openPanel();
    await sendMessage("Автомат до 10 тысяч долларов");
    const retry = [...host.querySelectorAll("[role='alert'] button")].find((button) => button.textContent === "Повторить") as HTMLButtonElement;
    await act(async () => retry.click());
    await flush();
    expect(posts).toHaveLength(2);
    expect(posts[1].message).toBe("Автомат до 10 тысяч долларов");
    expect(posts[1].history.some((item) => item.content === "Автомат до 10 тысяч долларов")).toBe(false);
    expect(userBubbles()).toHaveLength(1);
  });
  it("restores the conversation and filters from sessionStorage and keeps at most 20 messages", async () => {
    const stored = Array.from({ length: 25 }, (_, index) => ({ id: index + 1, role: index % 2 ? "assistant" : "user", text: `Сообщение ${index + 1}` }));
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ messages: stored, filters: { currency: "BYN", status: "draft" } }));
    stubFetch([() => Response.json(reply("Новый ответ."))]);
    await openPanel();
    expect(host.textContent).toContain("Сообщение 25");
    await sendMessage("Автомат до 10 тысяч долларов");
    expect(posts[0]).toMatchObject({ filters: { currency: "BYN" } });
    expect(JSON.stringify(posts[0])).not.toContain("draft");
    const saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "{}");
    expect(saved.messages).toHaveLength(20);
    expect(saved.messages.at(-1).text).toBe("Новый ответ.");
    expect(saved.filters).toEqual({ currency: "USD" });
  });
  it("ignores corrupt stored data", async () => {
    sessionStorage.setItem(STORAGE_KEY, "{not json");
    stubFetch([]);
    await openPanel();
    expect(host.textContent).toContain("Здравствуйте");
  });
});
