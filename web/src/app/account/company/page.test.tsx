import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ requireSession: vi.fn(), company: vi.fn() }));

vi.mock("@/lib/server", () => ({ requireSession: mocks.requireSession }));
vi.mock("@/lib/server-api", () => ({ serverApi: { company: mocks.company } }));
vi.mock("@/components/company-form", () => ({
  CompanyForm: ({ companyRole }: { companyRole?: string | null }) => <div data-company-role={companyRole || "unassigned"} />
}));

import AccountCompanyPage from "./page";

beforeEach(() => {
  mocks.requireSession.mockReset().mockResolvedValue({ user: { id: "member-1", company_role: "owner" } });
  mocks.company.mockReset().mockResolvedValue({ company: null });
});

describe("account company role context", () => {
  it.each(["owner", "admin", "seller", "viewer"])("passes the current %s company role from the session to the editor", async (companyRole) => {
    mocks.requireSession.mockResolvedValue({ user: { id: "member-1", company_role: companyRole } });

    const html = renderToStaticMarkup(await AccountCompanyPage());

    expect(mocks.requireSession).toHaveBeenCalledWith("/account/company");
    expect(html).toContain(`data-company-role="${companyRole}"`);
  });
});
