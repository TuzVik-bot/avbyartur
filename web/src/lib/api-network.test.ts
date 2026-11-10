import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClientError, api, apiRequest, resetCsrfToken, setCsrfToken } from "@/lib/api";

const NETWORK_MESSAGE = "Нет соединения с сервером. Проверьте интернет и повторите попытку.";

afterEach(() => {
  resetCsrfToken();
  vi.unstubAllGlobals();
});

async function rejection(promise: Promise<unknown>) {
  try {
    await promise;
  } catch (error) {
    return error;
  }
  throw new Error("expected the request to fail");
}

describe("API client network failures", () => {
  it("wraps a failed fetch in a Russian network ApiClientError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    const error = await rejection(apiRequest("listings"));

    expect(error).toBeInstanceOf(ApiClientError);
    expect(error).toMatchObject({ status: 0, code: "network", message: NETWORK_MESSAGE });
  });

  it("wraps a failed CSRF bootstrap fetch", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Load failed")));

    const error = await rejection(apiRequest("listings/drafts", { method: "POST", body: "{}" }));

    expect(error).toMatchObject({ code: "network", message: NETWORK_MESSAGE });
  });

  it("wraps a failed public capabilities fetch", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("NetworkError when attempting to fetch resource.")));

    const error = await rejection(api.guestContactEnabled());

    expect(error).toMatchObject({ code: "network", message: NETWORK_MESSAGE });
  });

  it("keeps aborted requests as aborts", async () => {
    const abort = new DOMException("The operation was aborted.", "AbortError");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(abort));
    setCsrfToken("csrf");

    const error = await rejection(apiRequest("listings"));

    expect(error).toBe(abort);
  });

  it("keeps pydantic error types and context from a 422 response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      code: "validation_error",
      message: "Проверьте правильность заполнения полей",
      field_errors: { title: "String should have at most 120 characters" },
      field_error_types: { title: "string_too_long" },
      field_error_context: { title: { max_length: 120 } },
      request_id: "req-1"
    }), { status: 422, headers: { "Content-Type": "application/json" } })));

    const error = await rejection(apiRequest("listings"));

    expect(error).toMatchObject({
      fieldErrorTypes: { title: "string_too_long" },
      fieldErrorContext: { title: { max_length: 120 } }
    });
  });
});
