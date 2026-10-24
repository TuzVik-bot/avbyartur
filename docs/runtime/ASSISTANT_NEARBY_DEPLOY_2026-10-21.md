# Помощник Авторынка: релиз 2026-10-21

## Результат

21 октября 2026 активирован web-only release `site-assistant-20261021-r1` на основе свежей копии production release `home-ux-20261016-r1`. В source candidate перенесены только замороженные `assistant.ts`, `assistant-server.ts` и соответствующие им два тестовых файла; web Compose overlay получил отдельный образ `avtorinok-web:site-assistant-20261021-r1`.

## Проверки сборки и источников

- Проверка review: PASS; блокирующих замечаний нет. Независимый прогон разработчика и ревьюера: 23/23 целевых unit-тестов.
- Production Docker build на VPS: Next.js compilation, TypeScript и генерация страниц завершились успешно.
- Итоговый source manifest: 725 файлов, SHA-256 `f338fa775463206a17e6f0bac06594e47121a0a6105a7dc87e96fb6c11b36f00`.
- Candidate image: `avtorinok-web:site-assistant-20261021-r1`, `linux/amd64`, image ID `sha256:1f0c384041dc5011404a49611c8a4240b0263709c7e3f2a5cbf1bf735c837132`.
- До активации `preswitch` прошёл: active release, контейнеры, volume identities, `.env`, rollback image, source manifest и Compose image set совпали с baseline.

## Активация и состояние production

- `/home/suite/apps/avtorinok` указывает на `/home/suite/apps/releases/site-assistant-20261021-r1`.
- Пересоздан только `avtorinok-web-1`; после запуска он healthy и использует candidate image. API, PostgreSQL, worker и test-mail остались на прежних контейнерах и образах; все пять сервисов healthy.
- Named volumes `avtorinok_postgres` и `avtorinok_private_media` не менялись. Runtime `.env` оставлен symlink на исходный release; target остаётся mode `600`, SHA-256 `16150470d4acd6374f0a04537664c49bbca695831207835e313066f134ef3d48`.
- `post` preflight прошёл. Миграции и записи в БД не выполнялись; снимок БД для этого web-only выпуска не создавался.
- Compose сообщил о старом остановленном orphan `avtorinok-web-candidate-20260929`; его не запускали и не удаляли.
- Общий HTTP Basic Auth, Nginx и правила индексации не менялись.

## Live assistant smoke

- `GET /` через локальный web listener: HTTP 200, `X-Robots-Tag: noindex, nofollow, noarchive`.
- `GET /api/assistant`: HTTP 200, `engine=ai`. Перед POST smoke проверено только булево условие free-маршрута: настроены ключ, модель с суффиксом `:free` и HTTPS endpoint `openrouter.ai`; значения ключа и конфигурации не выводились.
- Валютный конфликт: запрос «Покажи немного дороже в BYN» при активном максимуме `10000 USD` вернул HTTP 200, сохранил валюту и цену USD и попросил использовать валюту исходного бюджета либо выбрать новый бюджет.
- Относительное увеличение: «Да, покажи на 1000 рублей дороже» при активных `10000 BYN` и автоматической коробке вернуло HTTP 200, `engine=ai`, сохранило остальные фильтры и изменило бюджет на `10000.01–11000 BYN`.
- По публичному API production-каталог сейчас содержит 0 объявлений. Поэтому фактический ответ сообщил, что совпадений нет; nearby links не появились, так как нет реальных объявлений для них. Синтетические объявления не добавлялись.

## Доступность извне

Строгие HTTPS GET-проверки с VPS на `suite-s1.denjik.by/api/assistant` завершились ошибкой DNS (`gaierror`), а на `xn--80aeylebmo7f.xn--90ais/api/assistant` — `ConnectionRefusedError`. Проверки не отключали TLS-проверку и не меняли routing. Внешняя браузерная проверка production-домена на момент создания отчёта ещё выполняется; полное внешнее browser acceptance пока не подтверждено.

## Rollback

Проверенный rollback release: `/home/suite/apps/releases/home-ux-20261016-r1`; web image `avtorinok-web:home-ux-20261016-r1`, image ID `sha256:676ca0d4de48226917043150bf8d786376a01075189920bb8a2f47106c18341f`. Для отката приложения вернуть active symlink на этот release и выполнить только web service из его Compose-конфигурации с `--no-build --no-deps --wait`. БД, worker, test-mail и named volumes для web rollback не переключать.
