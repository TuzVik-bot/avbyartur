import { act, createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createRoot } from "react-dom/client";
import { describe, expect, it, vi } from "vitest";
import GlobalError from "./global-error";

describe("global error boundary", () => {
  it("renders its own Russian document because it replaces the root layout", () => {
    const html = renderToStaticMarkup(createElement(GlobalError, { error: new Error("private detail"), reset: () => {} }));

    expect(html).toContain('<html lang="ru">');
    expect(html).toContain("Что-то пошло не так");
    expect(html).toContain("Повторить");
    expect(html).toContain('href="/"');
    expect(html).not.toContain("private detail");
  });

  it("retries the failed render when the visitor presses «Повторить»", async () => {
    const reset = vi.fn();
    const container = document.createElement("div");
    document.body.append(container);
    const root = createRoot(container);
    vi.spyOn(console, "error").mockImplementation(() => {});

    await act(async () => { root.render(createElement(GlobalError, { error: new Error("boom"), reset })); });
    const button = [...document.querySelectorAll("button")].find((item) => item.textContent === "Повторить");
    await act(async () => { button?.click(); });

    expect(reset).toHaveBeenCalledOnce();
    act(() => root.unmount());
    container.remove();
    vi.restoreAllMocks();
  });
});
