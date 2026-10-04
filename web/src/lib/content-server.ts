import { serverApiRequest } from "@/lib/server-api";
import type { components } from "@/lib/types.generated";
import type { ContentKind } from "@/lib/content";

export const contentServerApi = {
  list: () => serverApiRequest<components["schemas"]["ManagedContentListOut"]>("admin/content?page_size=100"),
  public: (kind: ContentKind, key: string) => serverApiRequest<components["schemas"]["ManagedContentPublicEnvelope"]>(`content/${kind}/${encodeURIComponent(key)}`)
};
