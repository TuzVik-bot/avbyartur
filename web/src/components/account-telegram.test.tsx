import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AccountTelegram } from "@/components/account-telegram";
import { api } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      telegramStatus: vi.fn(),
      telegramLinkStart: vi.fn(),
      telegramUnlink: vi.fn(),
    },
  };
});

const telegramStatus = vi.mocked(api.telegramStatus);
const telegramLinkStart = vi.mocked(api.telegramLinkStart);
const telegramUnlink = vi.mocked(api.telegramUnlink);

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  telegramStatus.mockReset();
  telegramLinkStart.mockReset();
  telegramUnlink.mockReset();
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

const linked = { linked: true, linked_at: "2026-10-20T09:00:00Z", bot_username: "avtorinok_bot", channel_available: true };
const unlinked = { linked: false, linked_at: null, bot_username: "avtorinok_bot", channel_available: true };
const unconfigured = { linked: false, linked_at: null, bot_username: "", channel_available: false };

describe("account telegram section", () => {
  it("explains that the bot is not configured yet", async () => {
    telegramStatus.mockResolvedValue(unconfigured);
    await act(async () => { root.render(createElement(AccountTelegram)); });
    expect(container.textContent).toContain("Telegram-уведомления пока не настроены");
  });

  it("offers a linking code for an unlinked account", async () => {
    telegramStatus.mockResolvedValue(unlinked);
    telegramLinkStart.mockResolvedValue({ code: "link-code-123", bot_username: "avtorinok_bot" });
    await act(async () => { root.render(createElement(AccountTelegram)); });
    const start = [...container.querySelectorAll("button")].find((button) => button.textContent?.includes("Получить код"))!;
    await act(async () => { start.click(); });
    expect(telegramLinkStart).toHaveBeenCalledTimes(1);
    expect(container.textContent).toContain("@avtorinok_bot");
    expect(container.textContent).toContain("/start link-code-123");
  });

  it("shows the linked state and can unlink", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    telegramStatus.mockResolvedValue(linked);
    telegramUnlink.mockResolvedValue({ ...linked, linked: false, linked_at: null });
    await act(async () => { root.render(createElement(AccountTelegram)); });
    expect(container.textContent).toContain("Аккаунт привязан");
    const unlink = [...container.querySelectorAll("button")].find((button) => button.textContent?.includes("Отвязать"))!;
    await act(async () => { unlink.click(); });
    expect(telegramUnlink).toHaveBeenCalledTimes(1);
    expect(container.textContent).toContain("Telegram отвязан.");
  });
});
