import { serverApiRequest } from "@/lib/server-api";
import type { AdminTariffPage } from "@/lib/admin-tariffs";

function tariffListPath(page: number, pageSize: number) {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  return `admin/tariffs?${params.toString()}`;
}

export const adminTariffsServerApi = {
  list(page = 1, pageSize = 25) {
    return serverApiRequest<AdminTariffPage>(tariffListPath(page, pageSize));
  }
};
