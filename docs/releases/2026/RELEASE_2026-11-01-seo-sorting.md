# SEO и сортировка — 1 ноября 2026

Опубликовано по явному запросу пользователя. Production: https://xn--80aeylebmo7f.xn--90ais

## Релиз

- Активный каталог: `/home/suite/apps/releases/seo-sorting-20261101-r1`; ссылка `/home/suite/apps/avtorinok`.
- Основа: действовавший `google-verification-20261031-r1`, скопированный на сервере. Перенесены только файлы из `seo-sorting-20261101-r1/manifest.json`; точный diff сохранён в `production-delta.patch` рядом с manifest. Локальная грязная ветка целиком не публиковалась.
- API/worker: `avtorinok-api:seo-sorting-20261101-r1`, image ID `sha256:f72353ff5ccb17693dccb7aac2ca9a27bb7cc5b670884c18571607c79f8e33ca`.
- Web: `avtorinok-web:seo-sorting-20261101-r1`, image ID `sha256:5c874a34ee14110da18f3375e238e62a7a09c26abbbdf9d715c8bf2fa9521b86`.
- Compose project `avtorinok`: docker-compose.yml, docker-compose.override.yml, docker-compose.public-launch.yml, docker-compose.feedback.yml, docker-compose.yandex.yml, docker-compose.google.yml, docker-compose.seo-sorting.yml.
- API, worker, web healthy; `/health/ready` внутри API HTTP 200. Главная имеет ожидаемый Title; публичные заголовки без X-Robots-Tag noindex. SITE_ORIGIN — авторынок.бел, публичная индексация включена.
- `.env` — ссылка; целевой файл имеет права 600. Именованные тома `avtorinok_postgres`, `avtorinok_private_media` сохранены. Миграций, импорта, изменения Nginx и удаления данных не было.

## Изменения

- Восемь режимов: Актуальные (`newest`, прежний приоритет продвижения), Дешёвые, Дорогие, Новые объявления (`published_desc`, первая публикация), Старые объявления (`oldest`), С наименьшим пробегом, Новые по году, Старые по году. Сохраняются фильтры, сбрасывается страница. Неизвестный год/пробег в конце.
- Метаданные Title/canonical/robots выводятся в head без streaming. Для query-вариантов `/cars` — noindex,follow; отдельный page=1 нормализован на чистый адрес.
- Убрано удвоение марки модели; H1 «Продажа …», Title «Купить … в Беларуси».
- Фотографии объявлений получают alt «Продажа авто — название объявления — фото N» при отображении, включая существующие объявления; декоративные изображения остаются с пустым alt.
- Исправлена потеря первого символа при вводе марки/модели.
- Google tag G-48P5WKB0Z5 в общем head.
- Восстановлены разделы /buses, /trucks, /parts, /trailers; сохранены категория и контакты актуального production.
- Исправлены невалидные label/ARIA/SVG фрагменты HTML.
- Sitemap исключает служебные manual-* категории и страницы ниже общего порога индексации. Реальные объявления с manual-* в адресе и настоящие кириллические марки cur-unicode-* сохранены. Дата изменения/частота добавлены для каталога и статей; корневая запись согласована с canonical без завершающего слэша. После релиза: 1034 URL.

## Проверено

- Изолированная release-копия: 49 web-тестов, typecheck — успешно. Серверные Docker builds — успешно.
- Backend: 35 из 36 выбранных проверок успешны, включая пять новых режимов и проверку продвижения только для newest. Один старый тест `test_market_comparison_uses_one_analog_query_for_a_listing_page` падает также на неизменённой production baseline: ожидает UNION SQL, который текущая серверная реализация не выполняет. Это не изменение релиза.
- Интеграционные проверки использовали отдельный контейнер PostgreSQL `av-seo-sort-test-20261101` с tmpfs, БД `av_seo_sort_test`, без production-томов. Контейнер удалён после проверок.
- Независимый read-only обзор diff — замечаний не найдено. Статический secrets-check: два прежних ложных срабатывания в неизменённых compare-provider/ownership-calculator; новых в изменениях нет. Онлайн-проверка зависимостей не запускалась (зависимости не менялись).
- Production Playwright: восемь опций сортировки и API, порядок годов/пробега, сохранение condition и сброс page, query noindex, head metadata, модельные H1/Title, автоматический alt, GA один раз, sitemap, четыре категории и оба verification-файла HTTP 200.
- Отдельно: ввод Volvo/модели, сохранение фокуса, выбор; регистрационная форма со всеми полями и согласиями; мобильные ширины 320/375/390/430, фильтры марки/модели, раскрытие реального гостевого контакта и сохранение exchange intent. Никаких аккаунтов/объявлений/сообщений не создавалось.
- W3C production homepage: **0 errors**, 69 info, включая 11 warnings о карточках article без заголовка; прочее — trailing slash on void elements, формируемый React. Полный JSON рядом в validator.json.

## Оставшиеся вопросы

- Структура H2 главной ожидает пример пользователя; не переработана.
- Реальные названия отсутствующих каталожных моделей не выдумывались, записи не удалялись. Служебные категории закрыты и исключены из sitemap; исправление содержимого каталога требует достоверных названий.
- Доставка событий GA в кабинет Analytics и результаты индексации поисковиками этой проверкой не подтверждаются.

## Откат

Предыдущий каталог и образы сохранены. В `/home/suite/apps/releases/google-verification-20261031-r1` выполнить:

```sh
docker compose -p avtorinok \
  -f docker-compose.yml -f docker-compose.override.yml \
  -f docker-compose.public-launch.yml -f docker-compose.feedback.yml \
  -f docker-compose.yandex.yml -f docker-compose.google.yml \
  up -d --no-deps --no-build --wait api worker web
ln -s /home/suite/apps/releases/google-verification-20261031-r1 /home/suite/apps/avtorinok.rollback-next
mv -Tf /home/suite/apps/avtorinok.rollback-next /home/suite/apps/avtorinok
```

Затем проверить здоровье и реальную форму регистрации. Тома и базу не пересоздавать.
