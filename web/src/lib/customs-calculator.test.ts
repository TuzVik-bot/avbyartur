import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/lib/api";
import { calculateCustoms, getCustomsCalculatorMeta } from "@/lib/customs-calculator";

afterEach(() => {
  vi.unstubAllGlobals();
});

const meta = {
  scenario: "private_m1_personal_use_outside_eaeu",
  supported_currencies: ["EUR", "USD", "BYN", "RUB", "CNY"],
  supported_engines: ["petrol", "diesel"],
  calculation_available: false,
  unavailable_reason: "customs_rules_unverified",
  rules_version: null,
  verified_on: null,
  sources: [],
  scope_notes: []
} as const;

const request = {
  price_amount: "12500.75",
  currency: "USD",
  manufacture_date: "2020-04-12",
  engine_type: "diesel",
  engine_volume_cc: 1998,
  personal_use: true,
  origin_outside_eaeu: true
} as const;

describe("public customs calculator transport", () => {
  it("loads public metadata without entering the account CSRF flow", async () => {
    const fetchMock = vi.fn<typeof fetch>(async () => Response.json(meta));
    vi.stubGlobal("fetch", fetchMock);

    const result = await getCustomsCalculatorMeta();

    expect(result.calculation_available).toBe(false);
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/customs-calculator/meta");
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ method: "GET", credentials: "same-origin", cache: "no-store" });
  });

  it("posts the exact public request once without a CSRF bootstrap request", async () => {
    const fetchMock = vi.fn<typeof fetch>(async () => Response.json({ ...meta, calculation_available: true }));
    vi.stubGlobal("fetch", fetchMock);

    await calculateCustoms(request);

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/customs-calculator/calculate");
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("same-origin");
    expect(JSON.parse(String(init.body))).toEqual(request);
    const headers = new Headers(init.headers);
    expect(headers.get("content-type")).toBe("application/json");
    expect(headers.has("x-csrf-token")).toBe(false);
    expect(headers.has("idempotency-key")).toBe(false);
  });

  it("preserves the API error code and field details for Russian UI mapping", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>(async () => Response.json({
      code: "customs_rules_unverified",
      message: "Customs calculations are temporarily unavailable",
      field_errors: { manufacture_date: "invalid date" },
      request_id: "request-1"
    }, { status: 503 })));

    await expect(calculateCustoms(request)).rejects.toMatchObject({
      status: 503,
      code: "customs_rules_unverified",
      fieldErrors: { manufacture_date: "invalid date" },
      requestId: "request-1"
    });
    await expect(calculateCustoms(request)).rejects.toBeInstanceOf(ApiClientError);
  });
});
