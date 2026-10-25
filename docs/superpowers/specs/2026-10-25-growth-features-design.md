# Дизайн-док: пять ростовых функций портала (2026-10-25)

## Зачем

Пользователь попросил запустить доработку портала по пяти идеям из анализа мировых
автоклассифайдов (CarGurus, cars.com, auto.ru, mobile.de, Авито). Цель — больше
посетителей и больше поданных объявлений. Результат исследования кода: две из пяти
функций уже реализованы, поэтому работа смещена на недостающие части.

## Что уже есть (проверено в коде 2026-10-25)

- **Похожие объявления**: `GET /api/v1/listings/{id}/related` (`app/listing_discovery.py`),
  секция «Похожие объявления» в `web/src/components/listing-detail.tsx:215`, данные
  подтягиваются в `web/src/app/cars/[...slug]/page.tsx:126`. Функция готова — доработка не требуется.
- **Deal Rating (оценка цены)**: движок `app/market_pricing.py` (когорта марка/модель/
  кузов/КПП/топливо/поколение ±1 год, пробег ±10%, минимум 10 аналогов от 5 продавцов,
  защита от разброса IQR ≤ 50%). Бейджи «Цена ниже/выше рынка» показываются в поисковой
  выдаче (`listing-card.tsx`) и приходят в `price.market_comparison`. Чего нет: бейдж на
  странице самого объявления.

## Изменения

### 1. Бейдж рынка на странице объявления (малое)

- Frontend: `listing-detail.tsx` рендерит тот же `market-badge` из данных
  `listing.price.market_comparison` (API уже отдаёт). Никаких изменений API.

### 2. Instant-оценка своего авто («Сколько стоит моя машина?»)

- Backend: `app/valuation.py` — публичный расчётный модуль поверх market_pricing:
  когорта та же, но для лендинга допускается малая выборка с уровнями уверенности
  (≥10 аналогов и 5 продавцов → `high`; ≥4 аналога и 3 продавца → `low`; иначе `none`).
  Возвращает медиану и квартили в BYN (USD → BYN по свежему курсу), размер выборки,
  дату расчёта. Без персональных данных и без записи запросов.
- API: `GET /api/v1/market/valuation?make_id&model_id&year&mileage_km&condition&fuel&transmission&body_type_id&generation_id`
  → `MarketValuationOut {status: none|low|high, median_byn, p25_byn, p75_byn, sample_size, seller_count, as_of}`.
  Требует только публичные каталог-поля; анонимно; rate limit не нужен (один SELECT).
- Frontend: страница `/market-valuation` с формой (марка → модель → год → пробег →
  состояние) и результатом-вилкой; CTA «Разместить объявление» на `/sell?...`.
  Входные ссылки: главная и `/sell`.

### 3. Telegram-уведомления по сохранённым поискам

- Миграция `0026_telegram_channel`: `users.telegram_chat_id` (unique, nullable),
  `users.telegram_link_code`, `users.telegram_linked_at`; расширение check-констрейнтов
  `ck_saved_search_notification_channel`, `ck_notification_outbox_channel`,
  `ck_saved_search_notification_batch_channel` до `('email','web','telegram')`.
- Config: `telegram_bot_token: SecretStr = ""`, `telegram_api_url`, `telegram_timeout_seconds`.
- Воркер: связывание — периодический `getUpdates` (long poll) при заданном токене:
  команда `/start <code>` сопоставляется с `telegram_link_code`, записывает chat_id;
  доставка — ветка `channel == "telegram"` в `_deliver_notification` (sendMessage,
  простой текст + ссылка), идемпотентность через существующий outbox; отсутствие
  токена → `unsupported` как у email без провайдера.
- API: `GET /account/telegram/status`, `POST /account/telegram/link-start` (новый код),
  `POST /account/telegram/unlink`. CSRF обязателен для POST.
- Web: блок в `/account/settings` (шаги связывания, статус), опция «Telegram» в
  настройках уведомлений сохранённого поиска — видна только при привязанном чате.
  Канал `email` остаётся недоступным (email-провайдер не настроен) — без изменений.

### 4. Конфигурируемый платёжный провайдер и включение оформления

- Config: `payment_provider_name: str = ""`, `payment_callback_secret: SecretStr = ""`,
  `payment_checkout_url_template: str = ""` (плейсхолдеры `{order_id}`, `{amount}`,
  `{currency}`, `{description}`).
- `get_payment_provider()` возвращает `ConfiguredPaymentProvider` (обёртка над
  существующим `HmacPaymentProvider` с созданием чекаута по шаблону URL), когда заданы
  имя, секрет и шаблон; иначе — прежний `DisabledPaymentProvider`. Реальный провайдер
  (bePaid/ЕРИП) подключается владельцем через `.env` без правок кода.
- API: `GET /api/v1/billing/capabilities` → `{orders_enabled: bool}` (публично
  прочитаемое состояние для UI).
- Web: страница `/account/billing` — кнопка «Оформить» активна при
  `orders_enabled`, создаёт заказ (CSRF + Idempotency-Key) и редиректит на
  `checkout_url`; при выключенных заказах остаётся текущее состояние. Приём колбэков
  уже реализован (`POST /billing/callbacks/{provider}`).

## Не делаем (осознанно)

- Реальную интеграцию bePaid/ЕРИП SDK: нужны аккаунты, ключи и коммерческие условия
  владельца; делаем только настраиваемый шов (см. фичу 4).
- Telegram-webhook: требует изменений Nginx на VPS — отдельный запрос; используем polling.
- Email-доставку: провайдер не настроен, канал остаётся `unsupported`.
- Деплой на VPS: по договорённости требует отдельного явного запроса.

## Ограничения и риски

- Малые выборки: instant-оценка честно показывает «мало данных» вместо выдуманных цифр.
- Токен Telegram-бота — секрет владельца; до его задания канал недоступен и UI
  показывает шаги без обещаний доставки.
- Проверки: PostgreSQL-тесты на одноразовой `_test` БД для valuation, миграции 0026,
  доставки telegram и платёжного шва; web-тесты для страницы оценки, настроек Telegram
  и состояния кнопки оформления.
