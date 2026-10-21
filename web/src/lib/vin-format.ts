export type VinFormatResult =
  | { valid: true; normalized: string; message: string }
  | { valid: false; normalized: string; message: string };

const STANDARD_VIN_PATTERN = /^[A-HJ-NPR-Z0-9]{17}$/;

/** Checks only the common 17-character VIN shape; it does not authenticate a vehicle or its history. */
export function checkVinFormat(input: string): VinFormatResult {
  const normalized = input.trim().toUpperCase();

  if (!normalized) {
    return { valid: false, normalized, message: "Введите 17-символьный VIN." };
  }

  if (normalized.length !== 17) {
    return { valid: false, normalized, message: "Стандартный VIN содержит 17 символов. Проверьте номер по документам автомобиля." };
  }

  if (!STANDARD_VIN_PATTERN.test(normalized)) {
    return { valid: false, normalized, message: "Допустимы латинские буквы и цифры; буквы I, O и Q в стандартном VIN не используются." };
  }

  return {
    valid: true,
    normalized,
    message: "Формат стандартного 17-символьного VIN выглядит корректно. История автомобиля не проверена."
  };
}
