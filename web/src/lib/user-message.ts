import { ApiClientError } from "@/lib/api";

export type FieldErrorContext = Record<string, string | number | boolean>;

const CYRILLIC = /[А-Яа-яЁё]/;
// ApiClientError puts this text in place of a missing server message; it says nothing useful.
const CLIENT_DEFAULT_MESSAGE = "Запрос не выполнен";
const SERVER_ERROR_MESSAGE = "Сервер временно недоступен. Повторите попытку через несколько минут.";
const GENERIC_FIELD_MESSAGE = "Проверьте значение поля";
const CHOOSE_FROM_LIST = "Выберите значение из списка";

const CODE_MESSAGES: Readonly<Record<string, string>> = {
  network: "Нет соединения с сервером. Проверьте интернет и повторите попытку.",
  server_error: SERVER_ERROR_MESSAGE,
  internal_error: SERVER_ERROR_MESSAGE,
  authentication_required: "Войдите в аккаунт, чтобы продолжить.",
  unauthorized: "Войдите в аккаунт, чтобы продолжить.",
  invalid_session: "Сессия завершена. Войдите в аккаунт снова.",
  session_expired: "Сессия истекла. Войдите в аккаунт снова.",
  csrf_failed: "Сессия устарела. Обновите страницу и повторите действие.",
  invalid_credentials: "Неверный телефон, e-mail или пароль.",
  reauthentication_failed: "Пароль не подошёл. Проверьте его и повторите попытку.",
  invalid_otp: "Код не подошёл или истёк. Запросите новый код.",
  invalid_phone_change_otp: "Коды не подошли или устарели. Запросите новые.",
  recovery_invalid: "Ссылка для восстановления недействительна или устарела. Запросите новую.",
  email_verification_invalid: "Ссылка подтверждения недействительна или устарела. Запросите новое письмо.",
  rate_limited: "Слишком много попыток. Подождите немного и повторите.",
  validation_error: "Проверьте правильность заполнения полей.",
  not_found: "Не найдено. Возможно, запись удалена или ссылка устарела.",
  gone: "Объявление снято с публикации.",
  forbidden: "Недостаточно прав для этого действия.",
  account_unavailable: "Аккаунт недоступен. Обратитесь в поддержку.",
  listing_forbidden: "Это объявление нельзя изменить из вашего аккаунта.",
  owner_required: "Действие доступно только владельцу компании.",
  owner_protected: "Владельца компании нельзя изменить или удалить.",
  company_membership_required: "Действие доступно только сотрудникам компании.",
  company_not_approved: "Компания ещё не подтверждена модератором.",
  company_blocked: "Компания заблокирована. Обратитесь в поддержку.",
  company_role_read_only: "Ваша роль в компании позволяет только просмотр.",
  conflict: "Данные уже изменились. Обновите страницу и повторите.",
  revision_conflict: "Данные уже изменились. Обновите страницу и повторите.",
  idempotency_conflict: "Запрос уже обрабатывается. Подождите немного и обновите страницу.",
  idempotency_key_reused: "Запрос уже был отправлен. Обновите страницу.",
  listing_changed_retry: "Объявление изменилось. Обновите страницу и повторите.",
  invalid_listing_state: "Сейчас это действие с объявлением недоступно.",
  listing_not_editable: "Объявление сейчас нельзя редактировать.",
  listing_not_active: "Объявление сейчас не опубликовано.",
  photos_processing: "Фотографии ещё обрабатываются. Подождите немного.",
  photo_limit: "Достигнут лимит фотографий.",
  photo_too_large: "Фото слишком большое. Загрузите файл меньшего размера.",
  photo_pixel_limit: "У фото слишком большое разрешение.",
  invalid_photo: "Не удалось прочитать фото. Загрузите другой файл.",
  unsupported_photo: "Формат фото не поддерживается. Загрузите JPEG, PNG или WebP.",
  photo_mime_mismatch: "Формат фото не совпадает с расширением файла.",
  animated_photo: "Анимированные изображения не поддерживаются.",
  media_storage_unavailable: "Хранилище фото временно недоступно. Повторите попытку позже.",
  quota_exceeded: "Достигнут лимит объявлений по тарифу.",
  saved_search_limit: "Достигнут лимит сохранённых поисков.",
  self_chat: "Нельзя написать самому себе.",
  conversation_blocked: "Переписка заблокирована.",
  recipient_unavailable: "Собеседник сейчас недоступен.",
  phone_in_use: "Этот номер уже привязан к другому аккаунту.",
  email_unavailable: "Этот e-mail нельзя использовать.",
  invalid_phone: "Проверьте номер телефона.",
  contact_unavailable: "Контакт продавца недоступен.",
  registration_unavailable: "Регистрация временно недоступна. Повторите попытку позже.",
  sms_auth_unavailable: "Вход по SMS временно недоступен.",
  sms_provider_unconfigured: "Отправка SMS временно недоступна.",
  sms_delivery_uncertain: "Не удалось подтвердить отправку SMS. Подождите и запросите код снова.",
  email_provider_unconfigured: "Отправка писем временно недоступна.",
  billing_tariff_unavailable: "Тариф сейчас недоступен.",
  billing_tariff_capacity_unavailable: "Тариф сейчас недоступен для покупки.",
  invalid_billing_target: "Этот тариф нельзя применить к выбранному объявлению.",
  listing_not_promotable: "Это объявление сейчас нельзя продвигать.",
  promotion_overlap: "Для объявления уже действует продвижение.",
  order_not_paid: "Заказ ещё не оплачен.",
  payment_order_not_found: "Заказ не найден.",
  payment_order_unavailable: "Заказ недоступен для оплаты.",
  payment_amount_mismatch: "Сумма оплаты не совпадает с заказом. Обратитесь в поддержку.",
  payment_currency_mismatch: "Валюта оплаты не совпадает с заказом. Обратитесь в поддержку.",
  commerce_provider_unconfigured: "Оплата временно недоступна.",
  payment_provider_unavailable: "Оплата временно недоступна. Повторите попытку позже.",
  payment_provider_invalid_response: "Оплата временно недоступна. Повторите попытку позже.",
  exchange_rate_unavailable: "Курс валют временно недоступен. Повторите попытку позже.",
  customs_rates_unavailable: "Курсы валют временно недоступны. Повторите расчёт позже.",
  customs_rules_unavailable: "Расчёт таможенных платежей временно недоступен.",
  customs_rules_unverified: "Расчёт таможенных платежей временно недоступен.",
  request_body_too_large: "Слишком большой объём данных."
};

function plural(count: number, one: string, few: string, many: string): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

function contextValue(ctx: FieldErrorContext | undefined, key: string): string | number | undefined {
  const value = ctx?.[key];
  return typeof value === "number" || typeof value === "string" ? value : undefined;
}

function countText(ctx: FieldErrorContext | undefined, key: string, forms: [string, string, string]): string | undefined {
  const value = contextValue(ctx, key);
  const count = typeof value === "string" ? Number(value) : value;
  if (count === undefined || !Number.isInteger(count)) return undefined;
  return `${count} ${plural(count, ...forms)}`;
}

function boundText(ctx: FieldErrorContext | undefined, key: string, relation: string, fallback: string): string {
  const value = contextValue(ctx, key);
  return value === undefined ? fallback : `Значение должно быть ${relation} ${value}`;
}

// "Минимум 2 символа" uses nominative forms; "не более 2 символов" needs genitive ones.
const SYMBOLS: [string, string, string] = ["символ", "символа", "символов"];
const SYMBOLS_GENITIVE: [string, string, string] = ["символа", "символов", "символов"];
const VALUES: [string, string, string] = ["значения", "значений", "значений"];

const FIELD_MESSAGES: Readonly<Record<string, (ctx?: FieldErrorContext) => string>> = {
  missing: () => "Заполните это поле",
  string_too_short: (ctx) => { const text = countText(ctx, "min_length", SYMBOLS); return text ? `Минимум ${text}` : "Слишком короткое значение"; },
  string_too_long: (ctx) => { const text = countText(ctx, "max_length", SYMBOLS_GENITIVE); return text ? `Не более ${text}` : "Слишком длинное значение"; },
  too_short: (ctx) => { const text = countText(ctx, "min_length", VALUES); return text ? `Не менее ${text}` : "Слишком мало значений"; },
  too_long: (ctx) => { const text = countText(ctx, "max_length", VALUES); return text ? `Не более ${text}` : "Слишком много значений"; },
  greater_than: (ctx) => boundText(ctx, "gt", "больше", "Значение слишком маленькое"),
  greater_than_equal: (ctx) => boundText(ctx, "ge", "не меньше", "Значение слишком маленькое"),
  less_than: (ctx) => boundText(ctx, "lt", "меньше", "Значение слишком большое"),
  less_than_equal: (ctx) => boundText(ctx, "le", "не больше", "Значение слишком большое"),
  int_parsing: () => "Введите целое число",
  int_type: () => "Введите целое число",
  int_from_float: () => "Введите целое число",
  float_parsing: () => "Введите число",
  float_type: () => "Введите число",
  decimal_parsing: () => "Введите число",
  decimal_type: () => "Введите число",
  decimal_max_places: (ctx) => { const value = contextValue(ctx, "decimal_places"); return value === undefined ? "Слишком много знаков после запятой" : `Не более ${value} знаков после запятой`; },
  decimal_max_digits: () => "Слишком длинное число",
  uuid_parsing: () => CHOOSE_FROM_LIST,
  uuid_type: () => CHOOSE_FROM_LIST,
  enum: () => CHOOSE_FROM_LIST,
  literal_error: () => CHOOSE_FROM_LIST,
  bool_parsing: () => "Выберите «да» или «нет»",
  bool_type: () => "Выберите «да» или «нет»",
  string_type: () => "Введите текст",
  string_pattern_mismatch: () => "Значение указано в неверном формате",
  url_parsing: () => "Введите корректную ссылку",
  url_scheme: () => "Ссылка должна начинаться с http:// или https://",
  url_type: () => "Введите корректную ссылку",
  date_parsing: () => "Введите корректную дату",
  date_type: () => "Введите корректную дату",
  date_from_datetime_parsing: () => "Введите корректную дату",
  datetime_parsing: () => "Введите корректные дату и время",
  datetime_type: () => "Введите корректные дату и время",
  extra_forbidden: () => "Это поле не поддерживается",
  value_error: () => GENERIC_FIELD_MESSAGE
};

/** Russian text for a pydantic validation error type, using its context values when present. */
export function fieldErrorMessage(type: string, ctx?: FieldErrorContext): string {
  const build = FIELD_MESSAGES[type];
  return build ? build(ctx) : GENERIC_FIELD_MESSAGE;
}

export function hasCyrillic(text: string | undefined): boolean {
  return Boolean(text && CYRILLIC.test(text));
}

// Pydantic prefixes custom validator messages: "Value error, Укажите VIN".
const PYDANTIC_PREFIX = /^(Value error|Assertion failed),\s*/;

/**
 * Russian text per field of a 422 response. A Russian server text wins (custom validators),
 * then the pydantic error type, then a generic hint. English pydantic text is never shown.
 */
export function fieldMessages(error: ApiClientError): Record<string, string> {
  const fields = new Set([...Object.keys(error.fieldErrors), ...Object.keys(error.fieldErrorTypes)]);
  return Object.fromEntries([...fields].map((field) => {
    const raw = (error.fieldErrors[field] ?? "").replace(PYDANTIC_PREFIX, "").trim();
    if (hasCyrillic(raw)) return [field, raw];
    const type = error.fieldErrorTypes[field];
    return [field, type ? fieldErrorMessage(type, error.fieldErrorContext[field]) : GENERIC_FIELD_MESSAGE];
  }));
}

/** Russian text for any error shown to a user; `fallback` covers everything we cannot explain. */
export function userMessage(error: unknown, fallback: string): string {
  if (!(error instanceof Error)) return fallback;
  // Our own code throws Russian errors (client-side checks, server texts); browser and pydantic ones are English.
  if (hasCyrillic(error.message) && error.message !== CLIENT_DEFAULT_MESSAGE) return error.message;
  if (!(error instanceof ApiClientError)) return fallback;
  const known = Object.hasOwn(CODE_MESSAGES, error.code) ? CODE_MESSAGES[error.code] : undefined;
  if (known) return known;
  return error.status >= 500 ? SERVER_ERROR_MESSAGE : fallback;
}
