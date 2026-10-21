# Выкладка исправлений подачи объявления — 21 октября 2026

Пользователь разрешил: «задеплой всё». Активирован релиз `/home/suite/apps/releases/listing-create-20261021-r1` на основе актуального `competitive-first-wave-20261021-r1`. Сохранены уже развёрнутые помощник, сравнение и dealer feed UI. Включён весь патч PHOTO_UPLOAD_FIX_2026-10-21.patch: ручной ввод марки/модели, доступность ручной модели при пустом каталоге, продолжение обновления статуса фото, HEIF-коллекции в API и worker. Произвольные посторонние локальные доработки в релиз не переносились.

## Проверки

- Fresh SSH hostname: suite; active baseline и ID контейнеров повторно проверены перед переключением.
- Точечный патч применился к текущему production source без отказов.
- API и web собраны на VPS для linux/amd64. Production Next.js compilation, TypeScript, page generation PASS.
- Готовый API image принял HEIF с двумя изображениями и основным вторым кадром; compare route присутствует в OpenAPI.
- До релиза повторно пройдены 40 тестов формы; в предыдущем шаге 87 backend-тестов на отдельной одноразовой БД.
- API, web, worker пересозданы с тегом listing-create-20261021-r1; все healthy. DB и test-mail остались на прежних контейнерах.
- После релиза 207 объявлений, 102 фото ready; значения совпали с predeploy. Схема осталась 0031_contact_click_analytics; миграции и импорты не выполнялись.
- `.env` mode 600, checksum сохранена. Тома avtorinok_postgres и avtorinok_private_media сохранены. Nginx/Basic Auth/TLS не менялись.
- На основном HTTPS-домене авторынок.бел браузер открыл `/login?next=%2Fsell`: «Создать аккаунт» раскрывает имя/email/пароль/повтор/согласия и «Зарегистрироваться». Аккаунт не создавался. Снимок: listing-create-registration-live-2026-10-21.png.
- Публичные `/compare` и `/api/v1/auth/capabilities`: HTTP 200, email_registration=true. Один curl login получил timeout; браузерная проверка login успешна. Технический suite-s1.denjik.by по-прежнему имеет TLS unrecognized name.
- Авторизованный полный путь создания с фото проверен ранее локально; на production синтетические объявления не создавались. Нет оснований утверждать полную авторизованную browser acceptance в production.

## Backup / rollback

Backup: `/home/suite/apps/backups/listing-create-20261021-r1/database.pgdump`, 19,839,559 bytes, mode 600, SHA-256 `91eb589a4e7a047add149eafd1659914bdcdd3ca0aff8a809a21b62befa5fd47`; pg_restore --list проверен через DB-контейнер.

Предыдущий release и images: `/home/suite/apps/releases/competitive-first-wave-20261021-r1`. Rollback: атомарно вернуть `/home/suite/apps/avtorinok` на него и выполнить его Compose `up -d --no-build --no-deps --wait api worker web`. Старый worker image закреплён в прежнем override. БД и media при откате не восстанавливать автоматически.

Baseline/backup receipt/build logs сохранены на VPS в `photo-deploy-evidence/` нового релиза. Build smoke сначала остановился до переключения из-за обращения к .path у ленивого FastAPI router; исправлен на проверку OpenAPI. Следующий smoke прошёл, затем созданы backup и активация.

## Повторная проверка 2026-10-21 08:54 UTC

После сообщения пользователя об отсутствии изменений повторно проверено:
- Активный symlink и API/web/worker: listing-create-20261021-r1; контейнеры healthy.
- Публичный HTTPS-домен отдаёт `/_next/static/chunks/1qtwn2vufl7r2.js` с HTTP 200. SHA-256 `6a296637a1dd9fc29032e2463c199d725f848cca7d4278a195550cdd721e3f7f` совпадает с файлом работающего web-контейнера.
- Этот chunk указан в server/app/sell/page_client-reference-manifest.js. Содержит «Марки нет в списке», «Модели нет в списке», «Тип кузова можно выбрать ниже»; не содержит «Способ выбора марки».
- Маршрут /sell имеет private/no-store. В браузере без авторизации перенаправляет на /login?next=%2Fsell. Проверка формы в пользовательской авторизованной сессии остаётся необходимой; причина расхождения с наблюдением пользователя пока не установлена. Кеш браузера причиной не объявлялся.
