import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ publicContent: vi.fn() }));
vi.mock("@/lib/content-server", () => ({ contentServerApi: { public: mocks.publicContent } }));
vi.mock("@/components/login-form", () => ({
  LoginForm: (props: { nextPath: string; consentVersions?: { terms: string; privacy: string } | null }) => <div data-next={props.nextPath} data-terms={props.consentVersions?.terms || ""} data-privacy={props.consentVersions?.privacy || ""} />
}));

import LoginPage from "./page";

describe("login registration consent source", () => {
  it("passes only the published and approved legal document versions to registration", async () => {
    mocks.publicContent.mockReset()
      .mockResolvedValueOnce({ content: { status: "published", payload: { document_version: "terms-4", approved: true } } })
      .mockResolvedValueOnce({ content: { status: "published", payload: { document_version: "privacy-9", approved: true } } });
    const html = renderToStaticMarkup(await LoginPage({ searchParams: Promise.resolve({ next: "/account" }) }));

    expect(mocks.publicContent).toHaveBeenNthCalledWith(1, "legal_document", "terms_of_use");
    expect(mocks.publicContent).toHaveBeenNthCalledWith(2, "legal_document", "privacy_policy");
    expect(html).toContain('data-terms="terms-4"');
    expect(html).toContain('data-privacy="privacy-9"');
  });

  it("keeps registration consent unavailable when an approved document is missing", async () => {
    mocks.publicContent.mockReset().mockResolvedValueOnce({ content: { status: "published", payload: { document_version: "terms-4", approved: true } } }).mockRejectedValueOnce(new Error("not published"));
    const html = renderToStaticMarkup(await LoginPage({ searchParams: Promise.resolve({}) }));
    expect(html).toContain('data-terms=""');
    expect(html).toContain('data-privacy=""');
  });
});
