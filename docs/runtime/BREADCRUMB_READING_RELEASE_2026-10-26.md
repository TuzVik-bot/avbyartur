# Хлебные крошки и время чтения — 26 октября 2026

По запросу пользователя «задеплой» опубликован web-only релиз
`breadcrumb-reading-20261026-r1`.

## Изменения

- Ссылки марки/модели с техническим slug `manual-…` ведут на поиск:
  УАЗ → поиск «УАЗ», Patriot → поиск «УАЗ Patriot». Для справочных записей
  сохранены существующие URL; при ручной модели сохраняется фильтр марки.
- Одинаковые ссылки используются в интерфейсе и BreadcrumbList JSON-LD.
  Построитель JSON-LD поддерживает query string после проверки локального пути.
- В карточках и на странице статьи отображается «≈ N мин чтения»:
  1000 видимых символов в минуту, округление вверх, минимум одна минута.

## Исходники и сборка

Исходный production: `/home/suite/apps/releases/catalog-category-aware-20261025-r2`;
web `avtorinok-web:catalog-category-aware-20261025-indexed-r1`.
Кандидат создан копированием этого релиза и применением узкого патча.
Параллельные локальные изменения оценки стоимости и рыночных бейджей не включены.

Первая сборка обнаружила неполные `api.ts` / `server-api.ts` в серверных
исходниках: существующие компоненты ссылались на отсутствующие методы
(продвижение, отзывы, фото, мессенджеры). Эти два клиента восстановлены из
зафиксированного HEAD `9f42fe7`; сигнатура category-aware `catalog` сохранена
из серверного релиза. Backend при этом не менялся.

Повторная Docker production-сборка завершилась успешно.
Образ `avtorinok-web:breadcrumb-reading-20261026-r1`, linux/amd64,
ID `sha256:2a31e45f52c4a3891859c103c7b9a72d98448b6e503663d463b1493a3232cc4a`.
Действующий публичный режим `AVTORINOK_PUBLIC_INDEXING_ENABLED=true` сохранён.

## Проверки

- 36 целевых Vitest-тестов на исходниках кандидата: PASS
  (`SITE_ORIGIN=https://xn--80aeylebmo7f.xn--90ais`).
- Production build: PASS, включая TypeScript. Отдельный typecheck исходников
  со всеми тестами выявлял прежние несовпадения sell-form.test.tsx и FormFields;
  production-контекст исключает тестовые файлы штатным `.dockerignore`.
- `codex-security-check` изменённых helper/SEO/browser-script файлов:
  gitleaks PASS; Actions и online dependency scan не запускались.
- Браузерная проверка кандидата и затем production через SSH-туннель к Nginx:
  время чтения в карточках и статье видно; реальное объявление УАЗ Patriot
  открывается; обе ссылки крошек возвращают 200 и сохраняют объявление в выдаче.
- `/login?next=%2Fsell`: «Создать аккаунт» открывает имя, email, пароль,
  повтор пароля, согласия и кнопку «Зарегистрироваться». Форму не отправляли.
- `/healthz` и `/cars`: 200. Новый web healthy, RestartCount 0.
- ID контейнеров api/worker/db/test-mail до и после совпадают; все healthy.
  Тома `avtorinok_postgres` / `avtorinok_private_media` сохранены, `.env` — 600.
  Миграции, импорт данных и изменения Nginx не выполнялись.

Повторяемый браузерный сценарий:
`scripts/verify-breadcrumb-reading-release.py --base-url <URL> --artifacts <directory>`
(Playwright; при необходимости `--browser-executable <path>`).
Локальные артефакты проверки: `/tmp/av-breadcrumb-release/production-browser/`.
Временный контейнер кандидата после проверки удалён.

## Переключение и откат

Активная ссылка: `/home/suite/apps/avtorinok` →
`/home/suite/apps/releases/breadcrumb-reading-20261026-r1`.
Новый web image закреплён в `docker-compose.override.yml` и последнем
`docker-compose.public-launch.yml`. Проверка перед переключением подтвердила,
что итоговая конфигурация web отличается только image (без build context).
Пересоздан только web командой `up -d --no-deps --no-build --wait web`.

В новом релизе сохранены `deploy-backup/pre-deploy-state.json`,
`deploy-backup/web-source.sha256`, копии прежних Compose overlay.
Предыдущий релиз и web-образ сохранены. Для отката:

```sh
ln -s /home/suite/apps/releases/catalog-category-aware-20261025-r2 /home/suite/apps/avtorinok.rollback
mv -Tf /home/suite/apps/avtorinok.rollback /home/suite/apps/avtorinok
cd /home/suite/apps/releases/catalog-category-aware-20261025-r2
docker compose -f docker-compose.yml -f docker-compose.override.yml -f docker-compose.public-launch.yml up -d --no-deps --no-build --wait web
```

БД при web-only откате не восстанавливать; тома не удалять.
