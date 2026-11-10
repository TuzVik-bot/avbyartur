# Иллюстрации категорий — Web deploy 24 октября 2026

## Релиз

- Canonical site: `https://авторынок.бел/` (`xn--80aeylebmo7f.xn--90ais`).
- Release directory: `/home/suite/apps/releases/category-art-20261024-r2`.
- Web image: `avtorinok-web:category-art-20261024-r2`.
- Image ID: `sha256:fab68a2a0b3df0a045c51bb9ff8807b33245957a3ffd01d5827615837fb21fb2`.
- Platform: `linux/amd64`; image size: `100,503,523` bytes.
- Web build прошёл на VPS с `next build --webpack`: compile, TypeScript и
  генерация 11 статических страниц завершились успешно.
- Container switch выполнен под
  `/home/suite/apps/avtorinok-web-deploy.lock` с `--no-deps --no-build --wait`.
  Web r2 стал healthy. API и worker остались на
  `avtorinok-api:category-subcategories-20261024-r3`, PostgreSQL — на
  `postgres:17.11-alpine`; их image IDs не менялись. Named volumes сохранены.
- Runtime `.env` остался ссылкой на прежнюю цель, mode `600`. Миграций, импорта
  и записи в production data не было.
- Сохранены homepage-ads и footer overlays из точного текущего Compose набора
  category-subcategories r3. Старый orphan container `avtorinok-web-candidate-20260929`
  не удалялся.

## Изменения и проверка сборки

- В image включены 34 отдельных оптимизированных WebP иллюстрации, каждая
  размером 512×512 с alpha; sample PNG и исходники генерации не включены в
  runtime image. Все 34 WebP декодируются; каждый меньше 100 KB.
- Изменены consumer-файлы `web/src/components/category-landing.tsx` и
  `web/src/components/category-landing.module.css`. Иллюстрации подбираются по
  категории и подкатегории; узкий hero при ширине до 360 px остаётся в normal
  flow без обрезания и перекрытия.
- Отдельные component coverage изменения — в
  `web/src/components/category-landing.test.tsx` (7/7 targeted tests passed).
- Подробная таблица `{category, subcategory, path}` находится в
  `CATEGORY_ART_2026-10-24.md`; contact sheet —
  `CATEGORY_ART_CONTACT_SHEET_2026-10-24.png`.
- Первый immutable image r1 был заменён r2 после обнаружения трёх исходных
  1254×1254 WebP. Только `sowing.webp`, `post-harvest.webp` и
  `other-harvest.webp` пересобраны из сохранённых вне `public` PNG через
  `cwebp -q 90 -alpha_q 100 -resize 512 512`; новые файлы проверены как
  `512×512 yuva420p`. Остальные 31 WebP не менялись.
- Final r2 build context SHA-256:
  `a7ac8a862c2f2ded70b3580355c9431e3e06691f6349395d512a890f624bfcb4`.
- Перед включением проверено, что image содержит ровно 34 файла в
  `public/category-art` и не содержит `public/category-art/samples`.

## Rollback

Rollback возвращает только Web на проверенный предыдущий visual-fix образ
`avtorinok-web:category-art-20261024-r1` (ID
`sha256:01ab0e91c7d50128bbd1919df22f845958bdb743b07c3e15e16f07b27bcfe2d4`).
API/worker остаются на r3, БД и тома не восстанавливаются. Выполнять только
после проверки свежего lock/runtime:

```sh
ssh fortebit-prod 'flock -n /home/suite/apps/avtorinok-web-deploy.lock env AVTORINOK_IMAGE_TAG=category-subcategories-20261024-r3 AVTORINOK_WEB_IMAGE_TAG=category-art-20261024-r1 docker compose -p avtorinok --project-directory /home/suite/apps/releases/category-art-20261024-r2 -f /home/suite/apps/releases/category-art-20261024-r2/docker-compose.yml -f /home/suite/apps/releases/category-art-20261024-r2/docker-compose.override.yml -f /home/suite/apps/releases/category-art-20261024-r2/docker-compose.editorial-release.yml -f /home/suite/apps/releases/category-art-20261024-r2/docker-compose.moderation-release.yml -f /home/suite/apps/releases/category-art-20261024-r2/docker-compose.footer-release.yml -f /home/suite/apps/releases/category-art-20261024-r2/docker-compose.homepage-release.yml -f /home/suite/apps/releases/category-art-20261024-r2/docker-compose.category-release.yml up -d --no-deps --no-build --wait --wait-timeout 180 web'
```

## Публичная приёмка

GET-only acceptance r1: все 34 WebP URL вернули 200; пять category pages
прошли в light/dark, с ожидаемыми H1 и без browser/console errors или
mutating requests. На 320 px hero и изображение полностью оставались внутри
контейнера в обеих темах. После r2 отдельные GET трёх изменённых агро-assets
вернули 200; TLS/SNI проверка через `curl --resolve` использовала IP,
подтверждённый свежим Cloudflare DoH A lookup (canonical → `178.124.211.251`),
а streamed `ffprobe` подтвердил `512×512 yuva420p` для каждого файла. Повторный
аграрный screenshot в acceptance прошёл. Первоначальная ошибка браузерного DNS
была `ENOTFOUND`; HTTPS endpoint проверки через подтверждённый IP ответил 200,
так что это не указывает на недоступность origin.
