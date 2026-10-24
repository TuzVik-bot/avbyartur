# Категории и подкатегории — deploy 24 октября 2026

## Активный release

- Canonical URL: `https://авторынок.бел/` (`xn--80aeylebmo7f.xn--90ais`).
- Web release: `/home/suite/apps/releases/category-subcategories-20261024-r3`.
- Web image: `avtorinok-web:category-subcategories-20261024-r3`, ID
  `sha256:29c65b01bf6b24be3239ea1d531d6e80bcceab6dc9894acb6281b94a2346ab6c`.
- API and worker image: `avtorinok-api:category-subcategories-20261024-r3`, ID
  `sha256:e12de304e301314c6b87e2ad8d13fd711ed6d36c66c19673033c4b0c43c1793a`.
- Database: `postgres:17.11-alpine`, ID
  `sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24`.
- Release switch прошёл под `/home/suite/apps/avtorinok-web-deploy.lock` с
  `--no-deps --no-build --wait web`. Последующая read-only проверка показала
  все четыре сервиса healthy, deployment lock свободен, runtime `.env` mode
  `600`, volume `avtorinok_postgres` подключён. Второй volume
  `avtorinok_private_media` сохранён; переключение не меняло API, worker или DB.
- Релиз включает homepage-ads изменения из
  `/home/suite/apps/releases/homepage-ads-20261024-r1` и базовые изменения футера
  из `footer-compact-20261024-r1`. Для контекста см. отчёты
  `HOME_POPULAR_MAKES_ADS_DEPLOY_2026-10-24.md` и `FOOTER_DEPLOY_2026-10-24.md`.

## Проверки

- Web candidate собран для `linux/amd64`; Next compile и TypeScript проверки
  прошли, сгенерированы все 11 static pages, включая категории и `/sell`.
- API smoke: валидные `motorcycles/motorcycle` вернули 200; несовместимая
  `motorcycles/tractor` вернула 422 с ошибкой `subcategory`; неизвестная
  категория вернула 422 с ошибкой `category_code`. Значения объявлений не
  выводились.
- После переключения container health и image IDs совпали с release manifest.
- Публичный browser acceptance завершён: все проверки прошли. Category routes
  вернули 200; все пять реальных ссылок `&subcategory=` открыли GET с HTTP 200.
  Guest `/sell`→login next journeys сохранили category+subcategory.
- 20 проверок: пять category routes × viewport 1440/390 px × light/dark;
  все вернули 200 без горизонтального overflow. System theme корректно следовал
  эмулированным светлой и тёмной темам ОС. Browser page errors и небезопасные
  запросы не обнаружены.
- Auth capability `email_registration=true` и CSRF bootstrap вернули 200;
  раскрытая вкладка регистрации показала имя, email, пароль и повтор пароля,
  два обязательных согласия, ссылки на условия и кнопку регистрации. Отправка
  формы не выполнялась. Backend валидные пары вернули 200, невалидная пара и
  неизвестная категория — 422. System theme следовал эмулированной теме ОС.
- Публичная проверка подтверждает `X-Robots-Tag:
  noindex, nofollow, noarchive`; HTML meta robots показывает `index, follow`.
  Это существующее расхождение зафиксировано, настройки SEO в этой задаче не
  менялись. Не проверяй legacy `suite-s1.denjik.by` как production canonical.
- Пять filter API ответов содержали 0 публичных объявлений. Проверена поисковая
  поверхность; наличие результатов по инвентарю этим не подтверждается.
- Сводка acceptance и скриншоты сохранены в
  `/private/tmp/avtorinok-live-acceptance/` (`summary.json` и screenshots).
- Смена не выполняла миграций, импорта или записи в production data. Не
  включала HTTP Basic Auth; сохраняются `noindex` и авторизация личного кабинета.

## Rollback

Переключать только после проверки текущего lock и состояния контейнеров. Оба
варианта ниже используют `flock`; БД не восстанавливать для обычного отката
кода — релиз не добавляет миграций и не пишет данные.

Откат Web на сохранённый homepage-ads release, оставляя API и worker на r3:

```sh
ssh fortebit-prod 'flock -n /home/suite/apps/avtorinok-web-deploy.lock sh -c '\''AVTORINOK_IMAGE_TAG=category-subcategories-20261024-r3 AVTORINOK_WEB_IMAGE_TAG=homepage-ads-20261024-r1 docker compose -p avtorinok --project-directory /home/suite/apps/releases/category-subcategories-20261024-r3 -f /home/suite/apps/releases/category-subcategories-20261024-r3/docker-compose.yml -f /home/suite/apps/releases/category-subcategories-20261024-r3/docker-compose.override.yml -f /home/suite/apps/releases/category-subcategories-20261024-r3/docker-compose.editorial-release.yml -f /home/suite/apps/releases/category-subcategories-20261024-r3/docker-compose.moderation-release.yml -f /home/suite/apps/releases/category-subcategories-20261024-r3/docker-compose.footer-release.yml -f /home/suite/apps/releases/category-subcategories-20261024-r3/docker-compose.homepage-release.yml -f /home/suite/apps/releases/category-subcategories-20261024-r3/docker-compose.category-release.yml up -d --no-deps --no-build --wait --wait-timeout 180 web'\'''
```

Откат API и worker на проверенный кодовый baseline `product-wave-20261021-r1`,
не меняя Web r3:

```sh
ssh fortebit-prod 'flock -n /home/suite/apps/avtorinok-web-deploy.lock sh -c '\''AVTORINOK_IMAGE_TAG=product-wave-20261021-r1 docker compose -p avtorinok --project-directory /home/suite/apps/releases/product-wave-20261021-r1 -f /home/suite/apps/releases/product-wave-20261021-r1/docker-compose.yml -f /home/suite/apps/releases/product-wave-20261021-r1/docker-compose.override.yml up -d --no-deps --no-build --wait --wait-timeout 180 api worker'\'''
```

Сохраняй оба именованных volume. Не используй `down -v`, restore или изменение
Nginx для обычного отката образа.

## Backup

- Проверенный custom-format snapshot: `/home/suite/backups/avtorinok/category-subcategories-20261024/database.dump`.
- Размер: 20,978,024 bytes; parent directory mode `700`; файл mode `600`.
- SHA-256: `87d4df6c1f2b06e2f8770cfe7224e923c7763b30aa5eba47d476e7a1d49af7f1`.
- `pg_restore --list` прошёл (542 строки). Это safety snapshot; он не нужен для
  обычного image rollback.
