# Релиз UX — 5 октября 2026

Новый дизайн опубликован на https://suite-s1.denjik.by по явному запросу пользователя. GitHub-ветка: `codex/ux-redesign`. Коммит web: `94a0427357026d901fc91b1c4af106c5292ae95d`.

## Выпуск на момент проверки (позже заменён)

Этот UX-релиз позже сменил активный выпуск `marketplace-20261005T0956Z-baa9102`;
актуальная проверка и детали новой версии находятся в [DEPLOYMENT.md](../../DEPLOYMENT.md).

- Release: `/home/suite/apps/releases/ux-20261005T074032Z-94a0427`.
- AMD64 web image: `avtorinok-web:ux-20261005T074032Z-94a0427`.
- Обновлён только web. API/worker остались на `pilot-20261004T123401Z`, PostgreSQL — 17.11; все четыре контейнера healthy, RestartCount=0. API, worker и БД не пересоздавались.
- `.env` содержимое/права600, конфигурация Nginx, loopback-порты и named volumes проверены и сохранены. Общий Basic Auth остаётся выключенным; noindex и авторизация приложения сохранены.

## Проверки

- Локально443 web tests, typecheck, production build и204 браузерных случая для51 маршрута на320/390/768/1440px.
- На VPS оба web-образа собраны нативно AMD64. Отдельный кандидат прошёл проверку до переключения.
- На реальном HTTPS13 проверок: страницы и WebP200, noindex, отсутствие Basic Auth challenge, `/api/v1/me` и `/api/v1/admin/users` без сессии401.
- Production browser: новый desktop/mobile hero, существующая карточка с фотографиями, fullscreen filters и Escape. Поиск Mazda с бюджетом45000BYN вернул5 предложений без ошибки и горизонтального переполнения.
- Живой smoke выявил пропускcurrency в форме главной; исправлен скрытыйcurrency=BYN, регрессия5/5 и typecheck прошли, пересобран и опубликован коммит94a0427.

## Сохранение данных и откат

До/после релиза:202 объявления,102 фото,25 пользователей,0 компаний и тарифов; статусы100draft/100active/2paused. Активные записи с маркировкойAI-DEMO уже существовали до выкладки. Эта задача не импортировала объявления и не применяла миграции; БД остаётся0022_listing_categories.

Backup: `/home/suite/backups/avtorinok/pre-web-ux-20261005T071155Z-da936c3/avtorinok-20261005T072204Z`. ПровереныSHA256SUMS и читаемостьdump черезpg_restore --list.

Предыдущий UX выпуск: `/home/suite/apps/releases/ux-20261005T071155Z-da936c3`. Исходный выпуск: `/home/suite/apps/releases/pilot-20261004T123401Z`. Их источники/образы сохранены. Для отката переключитьactive symlink на выбранный сохранённыйrelease и выполнить `docker compose up -d --no-deps --no-build --wait web` из него. Не использоватьdown-v.

Квитанция: `deployment-receipt.json` в активномrelease. Только наш временный кандидат удалён; чужиеorphan containers,images,cache иvolumes не очищались.

Полная общепроектная нагрузочная приёмка, внешниеSMS/email/payment провайдеры и интеграция новых параллельных функцийorigin/main этим frontend-релизом не подтверждаются. Другие коммитыmain сохранены, веткаредизайна запушена отдельно.
