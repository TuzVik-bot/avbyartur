import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { InstallPrompt } from "./install-prompt";

type DeferredInstallEvent = Event & {
  prompt: ReturnType<typeof vi.fn>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
};

let root: Root;
let host: HTMLDivElement;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.restoreAllMocks();
});

function render() { act(() => root.render(<InstallPrompt />)); }

function dispatchInstallEvent(outcome: "accepted" | "dismissed" = "accepted") {
  const event = new Event("beforeinstallprompt", { cancelable: true }) as DeferredInstallEvent;
  event.prompt = vi.fn().mockResolvedValue(undefined);
  event.userChoice = Promise.resolve({ outcome, platform: "web" });
  act(() => window.dispatchEvent(event));
  return event;
}

describe("PWA install prompt", () => {
  it("shows only after the browser signals support and prompts from a user click", async () => {
    render();
    expect(host.querySelector("button")).toBeNull();

    const event = dispatchInstallEvent();
    const installButton = host.querySelector<HTMLButtonElement>('button[data-install-action="install"]');
    expect(event.defaultPrevented).toBe(true);
    expect(installButton).not.toBeNull();

    await act(async () => {
      installButton!.click();
      await event.userChoice;
    });

    expect(event.prompt).toHaveBeenCalledOnce();
    expect(host.querySelector("button[data-install-action=install]")).toBeNull();
  });

  it("lets the user dismiss the invitation without opening the browser prompt", () => {
    render();
    const event = dispatchInstallEvent();
    act(() => host.querySelector<HTMLButtonElement>('button[data-install-action="dismiss"]')!.click());

    expect(event.prompt).not.toHaveBeenCalled();
    expect(host.querySelector("[aria-label='Установить приложение']")).toBeNull();
  });

  it("hides when the app is installed by the browser", () => {
    render();
    dispatchInstallEvent();
    act(() => window.dispatchEvent(new Event("appinstalled")));

    expect(host.querySelector("[aria-label='Установить приложение']")).toBeNull();
  });
});
