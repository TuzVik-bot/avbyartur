# Калькулятор стоимости владения: web-релиз, 26 октября 2026

По явному запросу «задеплой — буду проверять на сервере» опубликован web-only релиз `ownership-calculator-20261026-r1`.

## Исходная точка и границы

Кандидат создан копированием активного `/home/suite/apps/releases/breadcrumb-reading-20261026-r1`. В него внесены только файлы калькулятора и три аддитивные ссылки: на главной в инструментах, в «Полезной информации» и рядом с ценой объявления. Live-изменения хлебных крошек, чтения статей и регистрации сохранены из исходного релиза. Параллельная оценка рыночной стоимости и другие локальные незакоммиченные изменения не включались.

Активный Compose flag `AVTORINOK_PUBLIC_INDEXING_ENABLED=true` сохранён в обоих overlay. HTML калькулятора сообщает `index, follow`; переключения индексации не было. Это отличается от общего правила `noindex` в `AGENTS.md`; текущий live-релиз до этой задачи уже был собран с включённой индексацией. Отключение индексации не входило в разрешённую задачу.

Изменён только web-контейнер. Backend/API, worker, база, миграции, данные объявлений, Nginx, авторизация, секреты и named volumes не изменялись.

## Сборка и проверки кандидата

- Web production image: `avtorinok-web:ownership-calculator-20261026-r1`, linux/amd64, image ID `sha256:4e9190bb6b1c8679b664c18527a0115fd613fff3df35248c059bafa7f404ed76`.
- Production build завершился успешно, включая TypeScript; маршрут `/ownership-calculator` включён.
- Локальные целевые тесты калькулятора, адаптера, страницы и формы: 39 passed (результат основной приёмки).
- Эфемерный кандидат на loopback вернул HTTP 200 для калькулятора, главной, страницы полезной информации и публичного объявления УАЗ 39099. На объявлении показана ссылка калькулятора; query `?listing=<UUID>` отрендерил заголовок, BYN-цену и сведения об источнике. Контейнер после проверки удалён.
- Сравнение итогового Compose с live project directory подтвердило изменение только `web.image`; определения сервисов, сетей и томов совпадают.

## Публикация и live-приёмка

Активная ссылка теперь ведёт на `/home/suite/apps/releases/ownership-calculator-20261026-r1`. Web пересоздан командой `up -d --no-deps --no-build --wait web`.

Публичная браузерная проверка на `https://xn--80aeylebmo7f.xn--90ais` прошла:

- `/ownership-calculator` открылся; примерный TCO изменился с 26 800 до 36 800 BYN при цене 40 000 BYN.
- Из реального объявления УАЗ 39099 CTA открыл калькулятор с названием и сохранённой ценой 13 442,07 BYN.
- В форме загрузили полную canonical-ссылку УАЗ Patriot вторым автомобилем. Название и цена 45 000 BYN определились; изменённая вручную цена первой машины 14 000 BYN сохранилась. Итоги сравнения: 20 734,76 и 32 800 BYN; разница 12 065,24 BYN.
- После релиза `/login?next=%2Fsell`: форма «Создать аккаунт» раскрыла имя, email, пароль, повтор пароля, оба согласия и кнопку «Зарегистрироваться». Отправку формы не выполняли.

После переключения все пять сервисов healthy, web RestartCount 0. Container ID и image ID `api`, `worker`, `db`, `test-mail` совпали с pre-deploy инвентаризацией. Томы `avtorinok_postgres` и `avtorinok_private_media` сохранены; API остаётся без опубликованного host port. Фактический `.env` — symlink на `/home/suite/apps/releases/home-ux-20261016-r1/.env`; целевой файл имеет mode 600 (сам symlink отображается как 777). Nginx и внешняя авторизация не менялись.

Серверный pre-deploy снимок состава контейнеров и томов: `deploy-backup/pre-deploy-state.json`. Копии двух исходных Compose overlay и SHA-256 лежат в `deploy-backup/` нового релиза. Source manifest калькуляторного delta: `474401b3727555595b92d53e4d612c0a73672abd45d53bf3b7ec68a2aeaf1fc6`.

## Откат

Предыдущий релиз `/home/suite/apps/releases/breadcrumb-reading-20261026-r1`, прежний image `avtorinok-web:breadcrumb-reading-20261026-r1` (`sha256:2a31e45f52c4a3891859c103c7b9a72d98448b6e503663d463b1493a3232cc4a`) и symlink `/home/suite/apps/avtorinok.ownership-rollback` сохранены.

```sh
ln -s /home/suite/apps/releases/breadcrumb-reading-20261026-r1 /home/suite/apps/avtorinok.rollback-next
mv -Tf /home/suite/apps/avtorinok.rollback-next /home/suite/apps/avtorinok
old=/home/suite/apps/releases/breadcrumb-reading-20261026-r1
docker compose --project-directory "$old" \
  -f "$old/docker-compose.yml" \
  -f "$old/docker-compose.override.yml" \
  -f "$old/docker-compose.public-launch.yml" \
  up -d --no-deps --no-build --wait web
```

Это откатывает только web. Базу данных и тома восстанавливать не нужно. Во время активации Compose сообщил об уже существующем orphan `avtorinok-web-candidate-20260929`; он не удалялся и не менялся.

## R2: округление суммы перепродажи

После первичной приёмки заметили косметическую ошибку представления: цена 13 442,07 × 60% показывалась как `8 065,241999999999`. Она исправлена округлением денежных seeds до двух знаков после запятой. В r2 изменён только `web/src/lib/ownership-listing.ts`; остальной live source скопирован из r1.

- Целевой набор тестов: 41/41 passed (четыре файла, включая регрессию для BYN/USD и перепродажи).
- Production build/TypeScript: PASS. Image `avtorinok-web:ownership-calculator-20261026-r2`, linux/amd64, ID `sha256:e52bb4b7bf6187c8e837c3ca4283346abcca17429f68d28e7578f00ec8074509`.
- Loopback-кандидат на реальном объявлении УАЗ 39099 вернул HTTP 200, цену 13 442,07 и сумму перепродажи `8 065.24`; длинное дробное значение отсутствовало.
- Публичная браузерная проверка после переключения подтвердила цену 13 442,07 BYN, перепродажу 8 065,24 BYN и итог 20 176,83 BYN.
- Активный symlink: `/home/suite/apps/releases/ownership-calculator-20261026-r2`. Предыдущий калькуляторный выпуск r1 сохранён, rollback symlink `/home/suite/apps/avtorinok.ownership-r2-rollback` указывает на него.
- Все пять сервисов healthy; web RestartCount 0. Container/image IDs api, worker, db и test-mail совпадают с r2 pre-deploy inventory в `deploy-backup/pre-deploy-state-r2.json`. Named volumes, `.env` (resolved target mode 600) и indexing flag `true` сохранены.
- r2 pre-deploy copies of Compose overlays: `deploy-backup/docker-compose.override.pre-r2.yml` и `deploy-backup/docker-compose.public-launch.pre-r2.yml`.

Для отката r2 на предшествующий калькуляторный r1:

```sh
ln -s /home/suite/apps/releases/ownership-calculator-20261026-r1 /home/suite/apps/avtorinok.rollback-next
mv -Tf /home/suite/apps/avtorinok.rollback-next /home/suite/apps/avtorinok
old=/home/suite/apps/releases/ownership-calculator-20261026-r1
docker compose --project-directory "$old" \
  -f "$old/docker-compose.yml" \
  -f "$old/docker-compose.override.yml" \
  -f "$old/docker-compose.public-launch.yml" \
  up -d --no-deps --no-build --wait web
```

Откат возвращает только web image и source r1; API, данные и тома менять не нужно.

## R3: восстановление оформления быстрых сценариев главной

После r2 быстрые ссылки под hero отображались без оформления и ломали мобильную раскладку. Диагностика live source и SSR показала точную причину: `page.tsx` передавал `className={styles.quickScenarios}`, но такого selector нет в `home.module.css`; в production SSR у nav отсутствовал `class`. При этом готовые стили `.quick-links` уже присутствовали в `globals.css`, включая `display:flex`, `flex-wrap:wrap` и стили ссылок. Сравнение r2 с `breadcrumb-reading-20261026-r1` показало, что homepage source отличался только добавленной ссылкой на калькулятор; `home.module.css`, `globals.css`, layout и search component совпадали. Переноса полной dirty homepage/CSS не было.

Исправление в r3 ограничено одной строкой homepage: nav подключён к существующему `className="quick-links"`. Остальная разметка, CSS, калькулятор и registration code не менялись.

- Production build и TypeScript: PASS. Image `avtorinok-web:ownership-calculator-20261026-r3`, linux/amd64, ID `sha256:5083d9867d7b8c23d08f6ed1487df766ff9a82b8d6533d602f4fd4cd0de49d97`.
- До переключения candidate SSR вернул `<nav class="quick-links" aria-label="Быстрые сценарии покупки">`.
- На публичной главной после переключения nav сохранил этот class; `/` и `/ownership-calculator` возвращают HTTP 200.
- Публичная визуальная проверка: при 356×780 hero не переполняет viewport, четыре быстрые ссылки выглядят кнопками в два ряда, заголовок переносится; при 1440 px кнопки находятся в один ряд. Скриншот: `/Users/home/.codex/visualizations/2026/10/25/01a174d0-dd21-75c2-a760-e5a5fb115a7f/ownership-calculator/menu-fixed-mobile.png`.
- Активный release: `/home/suite/apps/releases/ownership-calculator-20261026-r3`. Все пять сервисов healthy; web RestartCount 0. Container/image IDs `api`, `worker`, `db`, `test-mail` совпали с `deploy-backup/pre-deploy-state-r3.json`. Named volumes, `.env` целевой mode 600 и indexing flag `true` сохранены.
- Pre-deploy Compose overlays и inventory r3 находятся в `deploy-backup/`. При активации Compose сообщил о прежнем orphan `avtorinok-web-candidate-20260929`; он не менялся.

Для отката homepage hotfix r3 на калькуляторный r2:

```sh
ln -s /home/suite/apps/releases/ownership-calculator-20261026-r2 /home/suite/apps/avtorinok.rollback-next
mv -Tf /home/suite/apps/avtorinok.rollback-next /home/suite/apps/avtorinok
old=/home/suite/apps/releases/ownership-calculator-20261026-r2
docker compose --project-directory "$old" \
  -f "$old/docker-compose.yml" \
  -f "$old/docker-compose.override.yml" \
  -f "$old/docker-compose.public-launch.yml" \
  up -d --no-deps --no-build --wait web
```
