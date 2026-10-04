import { contentServerApi } from "@/lib/content-server";
import type { RegistrationConsentVersions } from "@/lib/api";

const VERSION_PATTERN = /^[A-Za-z0-9_.-]{1,80}$/;

export async function approvedConsentVersions(): Promise<RegistrationConsentVersions | null> {
  try {
    const [terms, privacy] = await Promise.all([
      contentServerApi.public("legal_document", "terms_of_use"),
      contentServerApi.public("legal_document", "privacy_policy")
    ]);
    const termsPayload = terms.content.payload;
    const privacyPayload = privacy.content.payload;
    const termsVersion = typeof termsPayload.document_version === "string" ? termsPayload.document_version : "";
    const privacyVersion = typeof privacyPayload.document_version === "string" ? privacyPayload.document_version : "";
    if (terms.content.status !== "published" || privacy.content.status !== "published" ||
      termsPayload.approved !== true || privacyPayload.approved !== true ||
      !VERSION_PATTERN.test(termsVersion) || !VERSION_PATTERN.test(privacyVersion)) return null;
    return { terms: termsVersion, privacy: privacyVersion };
  } catch {
    return null;
  }
}
