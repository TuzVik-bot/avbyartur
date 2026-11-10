import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { loadApprovedLegalDocument } from "@/lib/legal-documents";
import CookiePolicyPage from "./page";

vi.mock("@/lib/legal-documents", () => ({ loadApprovedLegalDocument: vi.fn() }));
beforeEach(() => vi.mocked(loadApprovedLegalDocument).mockReset().mockResolvedValue(null));

describe("cookie policy fallback", () => {
  it("states that analytics never runs in private sections and drops query and fragment", async () => {
    const text = new DOMParser().parseFromString(renderToStaticMarkup(await CookiePolicyPage()), "text/html").body.textContent ?? "";
    expect(text).toContain("не подключается в личном кабинете, администрировании, модерации, на страницах входа, восстановления пароля и подтверждения почты");
    expect(text).toContain("адрес сайта без пути, параметров запроса и фрагмента");
  });
});
