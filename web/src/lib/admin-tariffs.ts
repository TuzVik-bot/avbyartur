import { apiRequest } from "@/lib/api";

export type TariffServiceCode = "bump" | "highlight" | "top" | "dealer_package";
export type TariffCurrency = "BYN" | "USD";
export type TariffStatus = "active" | "disabled";

export type AdminTariff = {
  id: string;
  code: string;
  service_code: TariffServiceCode;
  name: string;
  amount: string;
  currency: TariffCurrency;
  duration_days: number;
  listing_quota: number | null;
  status: TariffStatus;
  revision: number;
  created_at: string;
  updated_at: string;
};

export type AdminTariffPage = {
  items: AdminTariff[];
  total: number;
  page: number;
  page_size: number;
};

export type AdminTariffCreateInput = {
  code: string;
  service_code: TariffServiceCode;
  name: string;
  amount: string;
  currency: TariffCurrency;
  duration_days: number;
  listing_quota: number | null;
  status: TariffStatus;
  reason: string;
  confirmation: "CREATE_TARIFF";
  current_password: string;
};

export type AdminTariffUpdateInput = {
  name: string;
  amount: string;
  currency: TariffCurrency;
  duration_days: number;
  listing_quota: number | null;
  status: TariffStatus;
  expected_revision: number;
  reason: string;
  confirmation: "UPDATE_TARIFF";
  current_password: string;
};

export type AdminTariffDeleteInput = {
  expected_revision: number;
  reason: string;
  confirmation: "DELETE_TARIFF";
  current_password: string;
};

export const adminTariffsApi = {
  create(data: AdminTariffCreateInput) {
    return apiRequest<{ tariff: AdminTariff; changed: boolean }>("admin/tariffs", {
      method: "POST",
      body: JSON.stringify(data)
    });
  },
  update(id: string, data: AdminTariffUpdateInput) {
    return apiRequest<{ tariff: AdminTariff; changed: boolean }>(`admin/tariffs/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(data)
    });
  },
  delete(id: string, data: AdminTariffDeleteInput) {
    return apiRequest<{ deleted: true }>(`admin/tariffs/${encodeURIComponent(id)}`, {
      method: "DELETE",
      body: JSON.stringify(data)
    });
  }
};
