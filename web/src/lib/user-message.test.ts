import { describe, expect, it } from "vitest";
import { ApiClientError } from "@/lib/api";
import { fieldErrorMessage, fieldMessages, userMessage } from "@/lib/user-message";

const FALLBACK = "Не удалось сохранить данные";

function apiError(status: number, code: string, message?: string) {
  return new ApiClientError(status, { code, message, field_errors: {}, request_id: "req-1" });
}

describe("userMessage", () => {
  it("translates known API error codes with English messages", () => {
    expect(userMessage(apiError(401, "authentication_required", "Authentication required"), FALLBACK)).toBe("Войдите в аккаунт, чтобы продолжить.");
    expect(userMessage(apiError(403, "csrf_failed", "CSRF validation failed"), FALLBACK)).toMatch(/Обновите страницу/);
    expect(userMessage(apiError(429, "rate_limited", "Too many requests"), FALLBACK)).toMatch(/Слишком много попыток/);
    expect(userMessage(apiError(401, "invalid_credentials", "Invalid credentials"), FALLBACK)).toMatch(/Неверный/);
    expect(userMessage(apiError(503, "payment_provider_unavailable", "Provider down"), FALLBACK)).toMatch(/Оплата/);
  });

  it("keeps a server message that is already in Russian", () => {
    expect(userMessage(apiError(409, "revision_conflict", "Тариф изменён; обновите список"), FALLBACK)).toBe("Тариф изменён; обновите список");
  });

  it("returns the fallback for unknown English errors and non-API errors", () => {
    expect(userMessage(apiError(400, "something_new", "Something went wrong"), FALLBACK)).toBe(FALLBACK);
    expect(userMessage(new TypeError("Failed to fetch"), FALLBACK)).toBe(FALLBACK);
    expect(userMessage(new Error("Request validation failed"), FALLBACK)).toBe(FALLBACK);
    expect(userMessage(new Error("Укажите цену с двумя знаками после запятой"), FALLBACK)).toBe("Укажите цену с двумя знаками после запятой");
    expect(userMessage("boom", FALLBACK)).toBe(FALLBACK);
    expect(userMessage(undefined, FALLBACK)).toBe(FALLBACK);
  });

  it("does not show the client default text for an empty error body", () => {
    expect(userMessage(new ApiClientError(400, {}), FALLBACK)).toBe(FALLBACK);
    expect(userMessage(new ApiClientError(502, {}), FALLBACK)).toMatch(/Сервер временно недоступен/);
  });

  it("explains network failures", () => {
    expect(userMessage(apiError(0, "network", "Нет соединения с сервером. Проверьте интернет и повторите попытку."), FALLBACK)).toBe("Нет соединения с сервером. Проверьте интернет и повторите попытку.");
    expect(userMessage(apiError(0, "network", "offline"), FALLBACK)).toMatch(/Нет соединения/);
  });
});

describe("fieldErrorMessage", () => {
  it("maps pydantic error types to Russian with context values", () => {
    expect(fieldErrorMessage("missing")).toBe("Заполните это поле");
    expect(fieldErrorMessage("string_too_short", { min_length: 2 })).toBe("Минимум 2 символа");
    expect(fieldErrorMessage("string_too_long", { max_length: 5000 })).toBe("Не более 5000 символов");
    expect(fieldErrorMessage("greater_than", { gt: 0 })).toBe("Значение должно быть больше 0");
    expect(fieldErrorMessage("greater_than_equal", { ge: 1900 })).toBe("Значение должно быть не меньше 1900");
    expect(fieldErrorMessage("less_than", { lt: 10 })).toBe("Значение должно быть меньше 10");
    expect(fieldErrorMessage("less_than_equal", { le: 2026 })).toBe("Значение должно быть не больше 2026");
    expect(fieldErrorMessage("int_parsing")).toBe("Введите целое число");
    expect(fieldErrorMessage("float_parsing")).toBe("Введите число");
    expect(fieldErrorMessage("uuid_parsing")).toBe("Выберите значение из списка");
    expect(fieldErrorMessage("enum", { expected: "'a' or 'b'" })).toBe("Выберите значение из списка");
    expect(fieldErrorMessage("literal_error")).toBe("Выберите значение из списка");
    expect(fieldErrorMessage("url_parsing")).toBe("Введите корректную ссылку");
    expect(fieldErrorMessage("too_long", { max_length: 3 })).toBe("Не более 3 значений");
    expect(fieldErrorMessage("too_short", { min_length: 1 })).toBe("Не менее 1 значения");
    expect(fieldErrorMessage("date_parsing")).toBe("Введите корректную дату");
    expect(fieldErrorMessage("value_error")).toBe("Проверьте значение поля");
  });

  it("uses Russian plural forms", () => {
    expect(fieldErrorMessage("string_too_short", { min_length: 1 })).toBe("Минимум 1 символ");
    expect(fieldErrorMessage("string_too_short", { min_length: 11 })).toBe("Минимум 11 символов");
    expect(fieldErrorMessage("string_too_long", { max_length: 22 })).toBe("Не более 22 символов");
  });

  it("falls back to a generic text without context or for unknown types", () => {
    expect(fieldErrorMessage("string_too_long")).toBe("Слишком длинное значение");
    expect(fieldErrorMessage("greater_than_equal")).toBe("Значение слишком маленькое");
    expect(fieldErrorMessage("brand_new_type")).toBe("Проверьте значение поля");
  });
});

describe("fieldMessages", () => {
  it("translates English pydantic texts and keeps Russian ones", () => {
    const error = new ApiClientError(422, {
      code: "validation_error",
      message: "Проверьте правильность заполнения полей",
      field_errors: {
        title: "String should have at most 120 characters",
        vin: "Value error, Укажите VIN из 17 символов",
        mileage: "Input should be a valid integer",
        name: "Не более 80 символов",
        odd: "Something unexpected"
      },
      field_error_types: { title: "string_too_long", vin: "value_error", mileage: "int_parsing", odd: "weird_type" },
      field_error_context: { title: { max_length: 120 } },
      request_id: "req-1"
    });

    expect(fieldMessages(error)).toEqual({
      title: "Не более 120 символов",
      vin: "Укажите VIN из 17 символов",
      mileage: "Введите целое число",
      name: "Не более 80 символов",
      odd: "Проверьте значение поля"
    });
  });

  it("uses a generic hint for English text without a type", () => {
    const error = new ApiClientError(422, { code: "validation_error", field_errors: { price: "Invalid value" } });

    expect(fieldMessages(error)).toEqual({ price: "Проверьте значение поля" });
  });
});
