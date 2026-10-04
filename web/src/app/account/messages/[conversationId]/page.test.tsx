import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  requireSession: vi.fn().mockResolvedValue({ user: { id: "buyer-1", display_name: "Покупатель", email: "buyer@example.test" } }),
  router: { push: vi.fn(), replace: vi.fn(), refresh: vi.fn() },
  user: { id: "buyer-1", display_name: "Покупатель", email: "buyer@example.test", role: "user" as const, company_id: null }
}));

vi.mock("next/link", () => ({ default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a> }));
vi.mock("next/navigation", () => ({ useRouter: () => mocks.router }));
vi.mock("@/components/auth-provider", () => ({ useAuth: () => ({ user: mocks.user }) }));
vi.mock("@/lib/server", () => ({ requireSession: mocks.requireSession }));

import ConversationPage from "./page";

describe("conversation thread route", () => {
  it("requires a session for the encoded thread path and renders its loading state", async () => {
    const html = renderToStaticMarkup(await ConversationPage({ params: Promise.resolve({ conversationId: "thread/1" }) }));

    expect(mocks.requireSession).toHaveBeenCalledWith("/account/messages/thread%2F1");
    expect(html).toContain("Загружаем переписку");
    expect(html).toContain("Не переводите предоплату");
  });
});
