# Выполнение плана продающего Авторынка

План: `docs/superpowers/plans/2026-10-23-selling-site-improvement.md`.

## Решения перед выполнением

- Исполнители: GPT-6 Luna, reasoning max; три независимых агента одновременно, затем следующие задачи и ревью.
- Рабочее дерево содержит большую незакоммиченную реализацию. Точечные изменения выполняются поверх неё с эксклюзивным владением файлами; перенос одного HEAD потерял бы существующие функции. Исходный tracked diff сохранён в `/private/tmp/avtorinok-pre-selling-plan.patch`; это не полный backup untracked-файлов.
- План является продуктовой дорожной картой, а не проверенной технической спецификацией. Несуществующие пути и обещания уточняются по исходному коду.
- Не обещать «5 минут», безопасность автомобиля или подтверждение продавца без доказательств.
- Отказ от измерения — выбор пользователя, а не ошибка. Нельзя включать аналитику принудительно.
- Размещение данных, deploy, миграции, внешние сообщения и договоры не входят в текущий запуск разработки.

## Разделение задач и зависимостей

| Задача | Владение | Зависимость / решение |
|---|---|---|
| 0.2 и 1.1: главная | page.tsx, home.module.css, page tests | Пустой каталог — честное состояние; не маскировать ноль фиктивными счётчиками |
| 1.2: пустая выдача | search-results и связанные search-state tests | Сначала существующие API; ссылки на ослабление фильтров не называть найденными результатами |
| 2.1: продавец | sell/page.tsx, собственные стили и тесты | Auth/next и защита редактирования сохраняются; не запрашивать приватные данные для гостя |
| 1.3 и 2.2: карточка | listing-detail и её тесты | Проверить уже реализованные действия; дата изменения не доказывает актуальность продавца |
| 3–4: доверие и рост | отдельная проверка покрытия | Не дублировать существующие механизмы; внешние зависимости явно отделить |

## Статусы

- [x] Главная и сценарии покупателя: first screen, four truthful shortcuts, separate API-error/empty states; no fabricated counters.
- [x] Пустая выдача: budget relaxation option +/-15% with filter/currency preservation and tests.
- [x] Путь продавца: guest landing, safe login return path, steps, photo requirements, noindex and tests.
- [x] Карточка объявления: modification date and seller-provided VIN context only when the public contract supplies VIN; no history-check claim.
- [x] Проверка оставшихся волн и конкретные зависимости: каталог, VIN, Telegram и подтверждение продавцов требуют внешних входных данных, перечисленных ниже.
- [x] Итоговые тесты, review и локальный preview текущих изменений: 102 файла / 612 web-тестов, typecheck, config-check и diff-check прошли. Независимый read-only review Luna не нашёл существенных новых регрессий.

## Findings that remain open

- Real catalog onboarding is blocked on a named partner, rights and a feed/photo contract. The current feed schema has no photo field, so importing rows alone does not satisfy the launch acceptance.
- Funnel measurement is not consent-gated: public listing views and contact reveals are recorded by the backend. Do not claim the planned measurement wave is complete until product/privacy decisions and an opt-out-aware event contract exist.
- Public seller verification/response-date badges are not supported by the current public API contract.
- VIN is intentionally not shown as “not specified” in public detail when the backend omits VIN; the public serializer removes the VIN field. A future non-sensitive `has_vin` field requires a separate API decision.
- SEO launch remains gated: root metadata is `noindex`, but sitemap/indexable route work in the dirty tree must be reviewed against the explicit public-launch decision before release.

## Продолжение разработки 23 октября

- Три исполнителя GPT-6 Luna с reasoning max: canonical/config, SEO пилота, кабинет статистики; отдельный Luna выполняет review.
- Default canonical и Compose fallback приведены к `https://авторынок.бел`; URL API нормализует домен в punycode. Явные локальные overrides сохраняются.
- Sitemap по умолчанию пустой и не запрашивает каталог. `AVTORINOK_PUBLIC_INDEXING_ENABLED=true` включает только генерацию и обнаружение sitemap; корневой noindex и HTTP-заголовки остаются. Robots допускает чтение noindex, скрывая ссылку на sitemap в пилоте.
- Удалён мёртвый клиент `public-stats` и его моки. Главная не показывает неподтверждённые показатели рынка.
- В кабинете статистики добавлены проверка календарных дат и периода, повтор загрузки с сохранением параметров и пояснения: просмотры не равны уникальным людям, показ телефона не равен звонку, чат не подтверждает сделку.
- Сбор новых событий с учётом согласия не реализован. Изменения кабинета не закрывают эту волну; существующие backend-события не менялись.
- Главная проверена в локальном браузере на desktop и mobile: горизонтального переполнения нет (375/375). На мобильном закрытая кнопка помощника перенесена в поток страницы, чтобы не перекрывать форму; открытый диалог остаётся всплывающим.
- Deploy, импорт, миграции и внешние отправки не выполнялись.
- Preview: `http://localhost:3011`; desktop/mobile главная и фактический robots проверены в браузере. CSS помощника дополнительно проверен после полного тестового прогона. Авторизованный кабинет проверен компонентными тестами, не реальным входом в аккаунт.

## Внешние входные данные

- Каталог: разрешённый источник/владелец, образец фида, права на фото, правила актуализации и снятия объявлений. Без них импорт не выполняется.
- VIN: выбранный поставщик, условия использования и обработки данных, sandbox, цена и правила возврата. Формат VIN не является историей автомобиля.
- Отзывы: подтверждённое основание взаимодействия и политика модерации; взаимодействие не считать сделкой.
- Telegram: согласие, привязка аккаунта, отписка, идемпотентность и проверяемая доставка.
- Публичный запуск: отдельное решение; noindex и обозначение пилота сохраняются.
