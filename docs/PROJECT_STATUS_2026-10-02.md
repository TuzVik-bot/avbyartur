# Авторынок — свежая проверка production 2 октября 2026

## Итог

**Весь текущий код задеплоен** в закрытый пилот https://suite-s1.denjik.by:
`pilot-20261002T133421Z`, схема `0021_dealer_feed_policy`. Проверять можно с
существующими доступами. Полная приёмка MVP не завершена: реальные провайдеры,
наполнение и ряд внешних условий отсутствуют; нагрузочный критерий остаётся открытым.

### Результат финального релиза

- Все4serviceshealthy/RestartCount0. BasicAuth/noindex,identical.envmode600,
  PostgreSQL/media volumes и существующие данные сохранены.
- Новые `/admin/tariffs`, `/admin/catalog-requests` и validation-policy API
  отвечают200; старые основные/кабинет/модерация/admin routes отвечают200.
- Production0018→0021 миграции прошли после чистой и0018upgrade/repeathead
  проверки на двух одноразовых локальных БД. К прежнему permission block не возвращаться.
- Source483backend/411web/typecheck/113opsPASS. Точные новые образы локально:
 29statefulAPI/worker checksPASS;8/8large32MPphotos при4concurrent готовы,
  health52/52HTTP200. NativePython3.12.15/Expat2.8.5/HEIF validationPASS.
- На реальном домене прошли browser smoke и47additionalAPI/newpages/roles/
  mobile checks. Ветки карточки/guest-favorite не исполнены на production:
  активных объявлений0. Это явно отмечено; вывод старого smoke PASS/skip
  не считается реальной проверкой карточки.
- Pre/postdeploybackup31SHA/readabledumpverified. Consistent backup tool
  кратко останавливает apps; первоначальный overlappingHTTPprobe получил502,
  послеbackup повторные domain/browser probes прошли. Причина не migration failure.
- Полные latest600sec/20RPS runs12000HTTP200 каждый, но p95goal<=500ms не
  достигнут:954.69/1285.03ms и670.15/978.96ms. Оба сохранены,fullMVPgateOPEN.
- GitHub authenticated,29доступныхрепозиториев проверены по имени; remote
  проекта не найден. Push ждёт URL, запрос отправлен пользователю.

Свежие квитанции: `release-133421-deployment-receipt.json`,
`release-133421-post-backup.json`, `release-133421-acceptance.json` в
`.superpowers/sdd/2026-10-01-project-completion/`.

Ниже сохранён предыдущий предрелизный срез. Его release/migration ожидания
исторические; текущий релиз описан выше и в `DEPLOYMENT.md`.

## Исторический срез до финального деплоя

- SSH аутентификация через существующий доступ успешна. Все четыре контейнера healthy, перезапусков 0.
- Активный релиз: `pilot-20261001T160530Z`; схема: `0018_profile_identity`.
- Production PostgreSQL проверен агрегирующими SELECT в транзакции READ ONLY: 100 draft, 2 paused, 0 active; компании 0, тарифы 0.
- Все 100 черновиков без фото. Каждое из двух приостановленных объявлений имеет готовое фото; всего 2 ready photo rows. Опубликованного каталога объявлений с фотографиями нет.
- Без Basic Auth сайт отвечает 401; с существующим доступом — 200. Заголовок noindex сохранён.
- Вход существующего администратора и `/api/v1/me` успешны. Значения учётных данных не выводились.
- HTTP 200: главная, `/cars`, `/dealers`, `/sell`, `/help`, `/about`, `/privacy-policy`, `/terms-of-use`, `/pro-subscription`, `/promotion`, `/account`, `/account/messages`, `/account/company`, `/moderation`, `/admin`, `/admin/users`, `/admin/catalog`, `/admin/content`, `/admin/settings`, `/admin/monitoring`, `/admin/audit`.
- HTTP 404: `/admin/tariffs`, `/admin/catalog-requests`, `/api/v1/listing-validation-policy`. Эти свежие функции не выпущены.
- Live auth capabilities: SMS login/registration, email notifications/verification, password recovery — false.

Открывающаяся страница подтверждает доступность маршрута, но не весь сценарий покупки, публикации, дилерского импорта, переписки или оплаты. В этом аудите не создавались объявления и не выполнялись импорт, миграции, платежи или рассылки.

## Незакрытые задачи

- Проверка миграции 0021 на двух выделенных одноразовых локальных БД остановлена автоматической проверкой разрешений; требуется ответ на ранее заданное точное разрешение. Обход не выполнялся.
- Новый кандидат `pilot-20261002T122033Z` собран на VPS из 471 проверенного файла: AMD64 API/web, Python 3.12.15 / Expat 2.8.5, обновлённые зависимости, i18n и проверки релиза. Offline OpenAPI/import/HEIF и изолированные web HTTP-проверки прошли. Preflight архива, Compose-тегов и старого релиза для отката прошёл. Production не переключён; приёмка с БД на новом образе не выполнена.
- Полная приёмка всех механик на последнем образе и обязательная десятиминутная нагрузочная проверка не завершены.
- Нет опубликованных реальных объявлений с фотографиями и компаний. Нужны разрешённые реальные данные и материалы.
- Реальные платежи, SMS, почта, внешний encrypted backup и мониторинг требуют завершения интеграций и проверки.
- Git push не выполнен: в текущем проекте нет `.git`, адрес репозитория не задан.

## Завершённая независимая работа

- I18n из §15: типизированный русский словарь, locale-aware URL/metadata и безопасные `/ru` aliases. Координатор: 411 web tests PASS, typecheck PASS.
- Шаблон деплоя больше не фиксирует старый тег. Preflight проверяет SHA и состав архива и итоговые Compose image tags, включая override; build context исключает локальные служебные/тестовые материалы. 14 focused preflight tests PASS; полный эксплуатационный прогон с настоящим age: 113 PASS, пропусков нет. Первый sandbox-прогон с PermissionError и 6 skip сохранён как неуспешный.
- Реальная проверка старого image показала Expat 2.7.1; новый digest-pinned Python image подтвердил исправленный Expat 2.8.5. Синтетическая HEIF-проверка не заменяет фото с настоящего телефона.
- Полный повтор старого exact Oct 1 image: 600 секунд, 12000/12000 HTTP 200, 20 RPS, p95 поиска 275.31 ms / карточки 294.20 ms — PASS при пороге 500 ms. Исходный провал сохранён. Это доказательство только старого search/detail baseline; latest-image и photo-upload load ещё не приняты.
- Курс USD на VPS за 2026-10-02: 3.005100 BYN, scale 1; совпадает с официальным НБРБ. Worker-задача обновления успешно завершена.

## Доступы

Подтверждены SSH, управление Docker, существующий Basic Auth и вход существующего администратора. Доступы и готовность внешних платёжных/SMS/почтовых/backup сервисов не подтверждены. Защищённые значения в отчёте не сохраняются.
