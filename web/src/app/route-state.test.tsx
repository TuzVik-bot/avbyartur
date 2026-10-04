import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AppError from "./error";
import AppLoading from "./loading";
import NotFound from "./not-found";
import AccountError from "./account/error";
import AccountLoading from "./account/loading";
import CarsError from "./cars/error";
import DealersError from "./dealers/error";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a>
}));

const error = new Error("upstream unavailable");

describe("route fallback states", () => {
  it("keeps a generic app loading fallback accessible", () => {
    const html = renderToStaticMarkup(createElement(AppLoading));
    expect(html).toContain('aria-busy="true"');
    expect(html).toContain("Загружаем страницу");
  });

  it("shows account loading context while account data is pending", () => {
    const html = renderToStaticMarkup(createElement(AccountLoading));
    expect(html).toContain("Загружаем кабинет");
    expect(html).toContain('aria-label="Загрузка кабинета"');
    expect(html).toContain("account-nav account-nav-loading");
  });

  it.each([
    [AppError, "Страница временно недоступна", "/cars"],
    [CarsError, "Не удалось загрузить поиск", "/"],
    [DealersError, "Не удалось открыть список компаний", "/cars"],
    [AccountError, "Не удалось открыть раздел кабинета", "/account"]
  ])("renders a retry and a safe destination for %s", (Component, heading, href) => {
    const html = renderToStaticMarkup(createElement(Component, { error, reset: vi.fn() }));
    expect(html).toContain('role="alert"');
    expect(html).toContain(heading);
    expect(html).toContain("Повторить");
    expect(html).toContain(`href="${href}"`);
  });

  it("renders a noindex not-found state with catalogue navigation", () => {
    const html = renderToStaticMarkup(createElement(NotFound));
    expect(html).toContain("Страница не найдена");
    expect(html).toContain('href="/cars"');
    expect(html).toContain('href="/"');
  });
});

describe("route error recovery", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    container = document.createElement("div");
    document.body.append(container);
    act(() => { root = createRoot(container); });
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it("uses the segment reset callback when account retry is clicked", async () => {
    const reset = vi.fn();
    await act(async () => { root.render(createElement(AccountError, { error, reset })); });
    await act(async () => { container.querySelector<HTMLButtonElement>("button")?.click(); });
    expect(reset).toHaveBeenCalledOnce();
  });
});
