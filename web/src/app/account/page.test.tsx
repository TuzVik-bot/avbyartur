import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  meListings: vi.fn(),
  favorites: vi.fn(),
  company: vi.fn(),
  requireSession: vi.fn()
}));

vi.mock("next/link", () => ({ default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a> }));
vi.mock("@/lib/server-api", () => ({ serverApi: mocks }));
vi.mock("@/lib/server", () => ({ requireSession: mocks.requireSession }));

import AccountPage from "./page";

describe("account overview failure state", () => {
  it("does not show zero counts when account data failed to load", async () => {
    mocks.requireSession.mockResolvedValue({ user: { display_name: "Тест", email: "pilot@example.test" } });
    mocks.meListings.mockRejectedValueOnce(new Error("offline"));
    mocks.favorites.mockRejectedValueOnce(new Error("offline"));
    mocks.company.mockRejectedValueOnce(new Error("offline"));

    const html = renderToStaticMarkup(await AccountPage());

    expect(html).toContain("Не удалось загрузить часть сведений кабинета");
    expect(html).toMatch(/href="\/account\/listings"[^>]*>[\s\S]*?Мои объявления <span>—<\/span>/);
    expect(html).toMatch(/href="\/account\/favorites"[^>]*>[\s\S]*?Избранное <span>—<\/span>/);
    expect(html).not.toMatch(/Мои объявления <span>0<\/span>/);
    expect(html).toContain("Сведения о компании недоступны");
  });
});
