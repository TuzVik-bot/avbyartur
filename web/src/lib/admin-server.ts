import { serverApiRequest } from "@/lib/server-api";
import type { components } from "@/lib/types.generated";
import type { AdminAuditItem, AdminAuditQuery, AdminOperations, AdminPage, AdminUser, AdminUsersQuery } from "@/lib/admin";
import type { AdminCatalogKind } from "@/lib/admin";

function queryPath(path: string, values: Record<string, string | number | undefined>) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

export const adminServerApi = {
  users(query: AdminUsersQuery = {}) {
    return serverApiRequest<AdminPage<AdminUser>>(queryPath("admin/users", {
      page: query.page ?? 1,
      page_size: query.page_size ?? 25,
      q: query.q?.trim(),
      role: query.role,
      status: query.status
    }));
  },
  audit(query: AdminAuditQuery = {}) {
    return serverApiRequest<AdminPage<AdminAuditItem>>(queryPath("admin/audit", {
      page: query.page ?? 1,
      page_size: query.page_size ?? 25,
      entity_type: query.entity_type?.trim(),
      entity_id: query.entity_id?.trim()
    }));
  },
  operations() {
    return serverApiRequest<AdminOperations>("admin/operations");
  },
  catalog(kind: AdminCatalogKind, query: { page?: number; page_size?: number; q?: string } = {}) {
    return serverApiRequest<components["schemas"]["AdminCatalogListOut"]>(queryPath(`admin/catalog/${encodeURIComponent(kind)}`, {
      page: query.page ?? 1, page_size: query.page_size ?? 25, q: query.q?.trim()
    }));
  },
  catalogVersions(kind: AdminCatalogKind, itemId: string, page = 1) {
    return serverApiRequest<components["schemas"]["AdminCatalogVersionListOut"]>(queryPath(`admin/catalog/${encodeURIComponent(kind)}/${encodeURIComponent(itemId)}/versions`, { page, page_size: 10 }));
  },
  settings() {
    return serverApiRequest<components["schemas"]["RuntimeSettingListOut"]>("admin/settings");
  }
};
