import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";
import { contentServerApi } from "@/lib/content-server";
import { loadApprovedLegalDocument } from "@/lib/legal-documents";
import { PublishedLegalDocument } from "@/components/published-legal-document";

vi.mock("@/lib/content-server", () => ({ contentServerApi: { public: vi.fn() } }));
afterEach(() => vi.resetAllMocks());

it("renders only server-approved documents and operator details as escaped plain text", async () => {
  vi.mocked(contentServerApi.public).mockResolvedValue({ content: { id: "doc", kind: "legal_document", key: "privacy_policy", status: "published", revision: 2, updated_at: "2026-10-01T00:00:00Z",
    payload: { approved: true, title: "Политика", document_version: "v2", body: "Правила обработки\n<script>не HTML</script>", operator: { legal_name: "Оператор", unp: "123456789", address: "Адрес", contact_email: "operator@example.com" } }
  }, indexable: false });
  const document = await loadApprovedLegalDocument("privacy_policy");
  expect(document).not.toBeNull();
  const html = renderToStaticMarkup(<PublishedLegalDocument document={document!} />);
  expect(html).toContain("123456789"); expect(html).toContain("v2");
  expect(html).toContain("&lt;script&gt;"); expect(html).not.toContain("<script>");
  expect(contentServerApi.public).toHaveBeenCalledWith("legal_document", "privacy_policy");
});

it("keeps draft fallback when provider is unavailable or document is unapproved", async () => {
  vi.mocked(contentServerApi.public).mockRejectedValueOnce(new Error("Unavailable"));
  expect(await loadApprovedLegalDocument("privacy_policy")).toBeNull();
  vi.mocked(contentServerApi.public).mockResolvedValue({ content: { id: "doc", kind: "legal_document", key: "terms_of_use", status: "published", revision: 1, updated_at: "2026-10-01", payload: { approved: false } }, indexable: false });
  expect(await loadApprovedLegalDocument("terms_of_use")).toBeNull();
});
