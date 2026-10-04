import { ApiClientError } from "@/lib/api";
import type { ApiErrorShape } from "@/lib/types";
import type { components } from "@/lib/types.generated";

export type CustomsCalculatorMeta = components["schemas"]["CustomsMetaResponse"];
export type CustomsCalculationRequest = components["schemas"]["CustomsCalculationRequest"];
export type CustomsCalculationResult = components["schemas"]["CustomsCalculationResponse"];

const API_PREFIX = "/api/v1/customs-calculator";

async function publicRequest<T>(path: string, init: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}/${path}`, {
      ...init,
      credentials: "same-origin",
      cache: "no-store",
      headers: new Headers(init.headers)
    });
  } catch {
    throw new ApiClientError(503, {
      code: "api_unavailable",
      message: "Сервис временно недоступен",
      field_errors: {},
      request_id: ""
    });
  }

  const payload: unknown = await response.json().catch(() => undefined);
  if (!response.ok) {
    throw new ApiClientError(response.status, (payload || {}) as Partial<ApiErrorShape>);
  }
  if (payload === undefined) {
    throw new ApiClientError(503, {
      code: "api_invalid_response",
      message: "Сервис вернул некорректный ответ",
      field_errors: {},
      request_id: ""
    });
  }
  return payload as T;
}

export function getCustomsCalculatorMeta(): Promise<CustomsCalculatorMeta> {
  return publicRequest<CustomsCalculatorMeta>("meta", { method: "GET" });
}

export function calculateCustoms(payload: CustomsCalculationRequest): Promise<CustomsCalculationResult> {
  return publicRequest<CustomsCalculationResult>("calculate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}
