import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  request: vi.fn(),
  requireSession: vi.fn()
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => <a href={href} {...props}>{children}</a>
}));
vi.mock("@/lib/server-api", () => ({ serverApiRequest: mocks.request }));
vi.mock("@/lib/server", () => ({ requireSession: mocks.requireSession }));
vi.mock("@/components/account-sessions", () => ({
  AccountSessions: ({ initialSessions }: { initialSessions: { id: string }[] | null }) => <div data-session-count={initialSessions?.length ?? "error"} />
}));
vi.mock("@/components/account-identity-controls", () => ({
  AccountIdentityControls: ({ initialProfile, initialConsents }: { initialProfile: unknown; initialConsents: unknown }) => <div data-identity-loaded={initialProfile && initialConsents ? "yes" : "no"} />
}));

import AccountSettingsPage from "./page";

describe("account settings page", () => {
  it("requires sign-in and loads the active session list", async () => {
    mocks.requireSession.mockResolvedValue({ user: { display_name: "Тест" } });
    mocks.request
      .mockResolvedValueOnce({ items: [{ id: "opaque-session-id" }] })
      .mockResolvedValueOnce({ profile: { id: "profile-1" } })
      .mockResolvedValueOnce({ items: [{ document_type: "terms" }] });

    const html = renderToStaticMarkup(await AccountSettingsPage());

    expect(mocks.requireSession).toHaveBeenCalledWith("/account/settings");
    expect(mocks.request).toHaveBeenNthCalledWith(1, "me/sessions");
    expect(mocks.request).toHaveBeenNthCalledWith(2, "me/profile");
    expect(mocks.request).toHaveBeenNthCalledWith(3, "me/consents");
    expect(html).toContain("Безопасность аккаунта");
    expect(html).toContain('data-session-count="1"');
    expect(html).toContain('data-identity-loaded="yes"');
  });

  it("renders an error-state panel when the sessions endpoint is unavailable", async () => {
    mocks.requireSession.mockResolvedValue({ user: { display_name: "Тест" } });
    mocks.request.mockRejectedValue(new Error("offline"));

    const html = renderToStaticMarkup(await AccountSettingsPage());

    expect(html).toContain('data-session-count="error"');
    expect(html).toContain('data-identity-loaded="no"');
  });
});
