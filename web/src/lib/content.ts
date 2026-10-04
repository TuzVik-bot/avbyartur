import { apiRequest } from "@/lib/api";
import type { components } from "@/lib/types.generated";

export type ContentItem = components["schemas"]["ManagedContentOut"];
export type ContentKind = ContentItem["kind"];
export type ContentVersion = components["schemas"]["ManagedContentVersionOut"];
export type ContentChange = components["schemas"]["ManagedContentChangeInput"];

export const contentApi = {
  list: () => apiRequest<components["schemas"]["ManagedContentListOut"]>("admin/content?page_size=100"),
  save: (kind: ContentKind, key: string, input: ContentChange) => apiRequest<components["schemas"]["ManagedContentEnvelope"]>(`admin/content/${kind}/${encodeURIComponent(key)}`, { method: "PUT", body: JSON.stringify(input) }),
  versions: (kind: ContentKind, key: string) => apiRequest<components["schemas"]["ManagedContentVersionsOut"]>(`admin/content/${kind}/${encodeURIComponent(key)}/versions`)
};
