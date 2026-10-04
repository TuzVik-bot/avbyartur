import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { AccountNav } from "@/components/account-nav";

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
});

describe("AccountNav", () => {
  it("links to saved searches and marks the current page", () => {
    act(() => { root.render(createElement(AccountNav, { current: "/account/saved-searches" })); });

    const link = container.querySelector<HTMLAnchorElement>('a[href="/account/saved-searches"]');
    expect(link).not.toBeNull();
    expect(link?.textContent).toContain("Сохранённые поиски");
    expect(link?.getAttribute("aria-current")).toBe("page");
  });

  it("links to messages and settings and marks the active destination", () => {
    act(() => { root.render(createElement(AccountNav, { current: "/account/messages" })); });

    const messages = container.querySelector<HTMLAnchorElement>('a[href="/account/messages"]');
    const settings = container.querySelector<HTMLAnchorElement>('a[href="/account/settings"]');
    expect(messages?.textContent).toContain("Сообщения");
    expect(messages?.getAttribute("aria-current")).toBe("page");
    expect(settings?.textContent).toContain("Настройки");
  });
});
