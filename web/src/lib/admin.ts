import { apiRequest } from "@/lib/api";
import type { components } from "@/lib/types.generated";

export type AdminRole = components["schemas"]["AdminUserOut"]["role"];
export type AdminMutableStatus = components["schemas"]["AdminUserChangeInput"]["status"];
export type AdminUser = components["schemas"]["AdminUserOut"];
export type AdminPage<T> = { items: T[]; total: number; page: number; page_size: number };
export type AdminAuditItem = components["schemas"]["AdminAuditEventOut"];
export type AdminOperations = components["schemas"]["AdminOperationsOut"];

export type AdminUsersQuery = {
  page?: number;
  page_size?: number;
  q?: string;
  role?: AdminRole;
  status?: string;
};

export type AdminAuditQuery = {
  page?: number;
  page_size?: number;
  entity_type?: string;
  entity_id?: string;
};

export type AdminUserUpdate = components["schemas"]["AdminUserChangeInput"];
export type AdminCatalogKind = components["schemas"]["AdminCatalogItemOut"]["kind"];
export type AdminCatalogItem = components["schemas"]["AdminCatalogItemOut"];
export type AdminCatalogChangeInput = components["schemas"]["AdminCatalogChangeInput"];
export type AdminCatalogVersion = components["schemas"]["AdminCatalogVersionOut"];
export type RuntimeSetting = components["schemas"]["RuntimeSettingOut"];
export type RuntimeSettingChangeInput = components["schemas"]["RuntimeSettingChangeInput"];

export const adminApi = {
  updateUser(id: string, data: AdminUserUpdate) {
    return apiRequest<{ user: AdminUser; changed: boolean }>(`admin/users/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(data)
    });
  },
  updateCatalogItem(kind: AdminCatalogKind, itemId: string, data: AdminCatalogChangeInput) {
    return apiRequest<{ item: AdminCatalogItem; changed: boolean }>(`admin/catalog/${encodeURIComponent(kind)}/${encodeURIComponent(itemId)}`, {
      method: "PATCH", body: JSON.stringify(data)
    });
  },
  catalogVersions(kind: AdminCatalogKind, itemId: string, page = 1) {
    return apiRequest<{ items: AdminCatalogVersion[]; total: number; page: number; page_size: number }>(
      `admin/catalog/${encodeURIComponent(kind)}/${encodeURIComponent(itemId)}/versions?page=${page}&page_size=10`
    );
  },
  updateRuntimeSetting(key: string, data: RuntimeSettingChangeInput) {
    return apiRequest<{ setting: RuntimeSetting; changed: boolean }>(`admin/settings/${encodeURIComponent(key)}`, {
      method: "PATCH", body: JSON.stringify(data)
    });
  }
};
