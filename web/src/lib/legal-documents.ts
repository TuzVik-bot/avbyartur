import { contentServerApi } from "@/lib/content-server";

export type ApprovedLegalDocument = {
  title: string; body: string; version: string;
  operator: { legal_name: string; unp: string; address: string; contact_email: string };
};

function isText(value: unknown): value is string { return typeof value === "string" && value.trim().length > 0; }

export async function loadApprovedLegalDocument(key: "terms_of_use" | "privacy_policy" | "cookie_policy"): Promise<ApprovedLegalDocument | null> {
  try {
    const result = await contentServerApi.public("legal_document", key);
    const payload = result.content.payload as Record<string, unknown>;
    const operator = typeof payload.operator === "object" && payload.operator !== null ? payload.operator as Record<string, unknown> : {};
    if (result.content.status !== "published" || payload.approved !== true || !isText(payload.title) || !isText(payload.body) || !isText(payload.document_version) ||
        !isText(operator.legal_name) || !isText(operator.unp) || !isText(operator.address) || !isText(operator.contact_email)) return null;
    return { title: payload.title, body: payload.body, version: payload.document_version,
      operator: { legal_name: operator.legal_name, unp: operator.unp, address: operator.address, contact_email: operator.contact_email } };
  } catch { return null; }
}
