import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("@/lib/server-api", () => ({ serverApiRequest: mocks.request }));

import { adminServerApi } from "@/lib/admin-server";

beforeEach(() => {
  mocks.request.mockReset().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
});

afterEach(() => {
  vi.restoreAllMocks();
  mocks.request.mockReset();
});

describe("admin server API", () => {
  it("encodes paginated user filters and trims free text", async () => {
    mocks.request.mockResolvedValueOnce({ items: [], total: 0, page: 2, page_size: 25 });
    await adminServerApi.users({ page: 2, page_size: 25, q: "  A+B test ", role: "user", status: "active" });
    expect(mocks.request).toHaveBeenCalledWith("admin/users?page=2&page_size=25&q=A%2BB+test&role=user&status=active");
  });

  it("builds a bounded audit query without empty filters", async () => {
    mocks.request.mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 25 });
    await adminServerApi.audit({ page: 1, page_size: 25, entity_type: " user ", entity_id: "8d21" });
    expect(mocks.request).toHaveBeenCalledWith("admin/audit?page=1&page_size=25&entity_type=user&entity_id=8d21");
  });

  it("encodes catalog kind, query, and version pagination", async () => {
    mocks.request.mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 25 });
    mocks.request.mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 10 });
    await adminServerApi.catalog("body-types", { q: "  4x4+SUV  " });
    await adminServerApi.catalogVersions("body-types", "id/1");
    expect(mocks.request).toHaveBeenNthCalledWith(1, "admin/catalog/body-types?page=1&page_size=25&q=4x4%2BSUV");
    expect(mocks.request).toHaveBeenNthCalledWith(2, "admin/catalog/body-types/id%2F1/versions?page=1&page_size=10");
  });

  it("loads runtime settings through the server API", async () => {
    mocks.request.mockResolvedValueOnce({ items: [] });
    await adminServerApi.settings();
    expect(mocks.request).toHaveBeenCalledWith("admin/settings");
  });
});
