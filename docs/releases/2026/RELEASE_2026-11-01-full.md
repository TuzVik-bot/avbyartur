# Общий релиз — 1 ноября 2026

Опубликован по запросу «задеплой всё» на https://авторынок.бел.

## Выпуск и состав

- Активная ссылка: `/home/suite/apps/avtorinok` → `/home/suite/apps/releases/full-20261101-r1`.
- Основа — свежая серверная копия `seo-sorting-20261101-r1`; сверены все локальные изменённые и новые backend/web/scripts/catalog-файлы.
- API/worker: `avtorinok-api:full-20261101-r1`, image ID `sha256:b027767ef6933a7148b7dbee826e036d876ec40325447fc8bf229c259abcd4fa`.
- Web: `avtorinok-web:full-20261101-r1`, image ID `sha256:2c0400168ec16cc6deefd3edcdf69c38f66b940067f5c3037184b5b61f25a97e`.
- Точный delta: `full-20261101-r1/manifest.json`, 20 файлов. SHA-256 архива: `59626c1465c3c8fa6effc454e5e639477cabc858b7546d6d6685f34c00094be1`.
- Включены инструменты Onliner, проверки каталога и production, исправление сохранения ручных моделей при обновлении Wikidata, актуальный отчёт покрытия seed и дополнительные проверки интерфейса.
- Большинство локальных изменений уже было опубликовано. Сохранены более новые production-категории, независимые контакты мессенджеров, сортировки, SEO, регистрация, усиленный импортёр Škoda и используемое fallback-изображение. Наложение старой локальной версии откатило бы эти функции; при сборке использовался текущий серверный вариант.
- Дублирующий эффект поиска моделей и повторное CSS-правило, возникавшие при автоматическом объединении, не включены.
- Новых зависимостей нет. Миграций, повторного импорта каталога, изменения Nginx, удаления данных и томов не выполнялось. Локальные изменения и артефакты других задач сохранены.

## Проверки

- Сборки API и web: PASS; source manifest на сервере: PASS; Compose config: PASS.
- TypeScript typecheck: PASS.
- Onliner planner: 12 PASS; Wikidata: 13 PASS.
- Backend catalog/policy на отдельном PostgreSQL с tmpfs, БД `av_full_release_test`: **27 PASS**. Два устаревших ожидания seed 253 обновлены на фактические 294; контейнер тестовой БД удалён.
- Полный web baseline: 663 PASS / 50 FAIL; candidate: 683 PASS / 49 FAIL. Новых имён падающих тестов нет. Полный набор не зелёный: прежние тесты расходятся с текущим production UI, категориями, контактами и калькулятором. Релиз не объявляется прошедшим полный suite. Повторный узкий запуск также воспроизвёл прежнее ожидание телефона в review-форме.
- Secrets scan новых исполняемых инструментов: PASS; Actions и зависимости не менялись.
- Публичный HTTPS: Title `Автомобили Беларуси`, AURUM отсутствует.
- Production browser: Jaguar, шесть основных моделей, выбор XF и поиск «Ягуар» PASS.
- Production browser: восемь сортировок/API-порядок, сохранение фильтра и сброс страницы, query noindex, head metadata, GA, alt, модельные H1/Title, sitemap (1 034 URL), четыре раздела и оба verification-файла PASS.
- Реальная регистрационная форма: все поля/согласия и кнопка регистрации PASS; аккаунт не создавался.
- Mobile 320/375/390/430: кабинет, фильтры марки/модели, раскрытие существующего гостевого контакта и exchange intent через login PASS. Контактные данные не записывались в отчёт.
- Все пять контейнеров healthy; `/health/ready` API: `{"status":"ok"}`.
- Каталог после релиза: **482 марки / 7 046 моделей**. `avtorinok_postgres` и `avtorinok_private_media` сохранены; `.env` target mode 600, содержимое не читалось.
- Сохранён действующий публичный режим индексации из предыдущего релиза; общий Basic Auth не включался.

## Резервная копия и откат

Свежая копия: `/home/suite/backups/avtorinok/full-20261101-r1/` — custom database dump, seed/coverage, точные прежние image IDs и release path. Дамп прочитан `pg_restore -l`; пять checksum entries PASS. Медиа не изменялись, прежний именованный том сохранён. Это не полный restore drill.

Для отката приложения, без восстановления старой БД:

```sh
cd /home/suite/apps/releases/seo-sorting-20261101-r1
docker compose -p avtorinok \
  -f docker-compose.yml -f docker-compose.override.yml \
  -f docker-compose.public-launch.yml -f docker-compose.feedback.yml \
  -f docker-compose.yandex.yml -f docker-compose.google.yml \
  -f docker-compose.seo-sorting.yml \
  up -d --no-deps --no-build --wait api worker web
ln -s /home/suite/apps/releases/seo-sorting-20261101-r1 /home/suite/apps/avtorinok.rollback-full
mv -Tf /home/suite/apps/avtorinok.rollback-full /home/suite/apps/avtorinok
```

После отката проверить регистрацию, каталог и здоровье. Каталог Onliner уже находился в БД до этого релиза и сохраняется при откате приложения.
