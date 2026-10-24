# Первая очередь конкурентных сценариев — выпуск 21 октября 2026

## Итог

Выпуск `competitive-first-wave-20261021-r1` активирован. Ссылка
`/home/suite/apps/avtorinok` указывает на
`/home/suite/apps/releases/competitive-first-wave-20261021-r1`.

После активации API и web healthy. Сравнение объявлений отвечает через API и
web; неавторизованный доступ к кабинету импорта дилерских фидов отклоняется.
База данных, worker, test-mail, тома, `.env`, Nginx и TLS-конфигурация не
переключались. Миграции, восстановление backup и импорт данных не выполнялись.

## Образы и активные контейнеры

| Сервис | Контейнер | Image ID | Состояние |
| --- | --- | --- | --- |
| API | `c1e0acb2a9e2` | `sha256:b614ba540a96f709e252c83d96a4a3d59117a72645bfa9dd2db112abce3f8504` | healthy |
| Web | `a0d2dfeffdbc` | `sha256:2337cbaecfb5db06ec6407b8d2d35b617942fdf42f09c3c4facbb85c9f369a55` | healthy |
| DB | `3b1b565d1946` | `sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24` | healthy, прежний контейнер |
| Worker | `04359de26a71` | `sha256:85da515e091935761ce7e85e05714a2892d88a9e7c3a8143bab185f051d50bf1` | healthy, прежний контейнер |
| Test-mail | `96178b7afaf7` | `sha256:b68349e3a014b90c5610bfb26b2ae36f3892d7b8cf25ee140c6c71c98d2fcf48` | healthy, прежний контейнер |

Новые образы собраны для `linux/amd64`. Worker оставлен на теге
`pilot-catalog-product-20261015T1241Z`. Именованные тома
`avtorinok_postgres` и `avtorinok_private_media` сохранили прежние имена и
mountpoint. Runtime `.env` остался прежним: режим `600`, SHA-256
`16150470d4acd6374f0a04537664c49bbca695831207835e313066f134ef3d48`.

## Backup и откат

Перед активацией создана и проверена копия базы:

- `/home/suite/apps/backups/competitive-first-wave-20261021/avtorinok-db-20261021.pgdump`
- размер `19,839,435` байт, режим `600`;
- SHA-256 `297acdd600ee33350b0fbbc3fb9269341ecc9653c31e31416c1cfdad4f50aade`;
- предварительная проверка `pg_restore --list` показала 516 записей каталога.

При финальном read-only снимке на VPS команда `pg_restore` отсутствовала, поэтому
повторный перечень каталога backup не выполнялся. Размер и checksum совпали с
предварительной проверкой.

Rollback приложения — вернуть ссылку на сохранённый релиз
`/home/suite/apps/releases/site-assistant-20261021-r1` и поднять из его Compose
конфигурации только API и web со старыми образами:

```sh
apps=/home/suite/apps
release=$apps/releases/site-assistant-20261021-r1
tmp=$apps/.avtorinok-link.rollback
ln -s "$release" "$tmp"
mv -Tf "$tmp" "$apps/avtorinok"
(cd "$release" && docker compose --project-directory "$release" \
  --env-file "$release/.env" -p avtorinok \
  -f "$release/docker-compose.yml" \
  -f "$release/docker-compose.override.yml" \
  up --no-build --no-deps --wait api web)
```

Не удалять тома и не запускать `docker compose down -v`. Worker, DB, test-mail,
`.env` и данные при rollback не переключать.

## Проверки

### Подготовка кандидата

- Service-aware release preflight прошёл: Compose-конфигурация указывала на
  candidate API/web tags и прежний worker tag. Самопроверка валидатора отвергала
  неверные API/web tags и посторонний worker tag.
- Изолированный smoke кандидата подтвердил импорт приложения API и наличие
  маршрутов сравнения и dealer feed-imports; web `/compare` вернул `200`,
  `noindex`, заголовок и пустое состояние.
- Эта квитанция не утверждает повторный полный прогон `pytest`, frontend tests
  или typecheck на рабочем checkout. Production-образы проверялись отдельно от
  локального рабочего дерева.

### После активации

- API `GET /api/v1/listings/compare?ids=00000000-0000-0000-0000-000000000000`:
  `200`, `{"items":[]}`.
- API `GET /api/v1/dealer/feed-imports` без cookie: `401`.
- Web `/compare`: `200`, заголовок
  `X-Robots-Tag: noindex, nofollow, noarchive`, присутствуют заголовок страницы
  и пустое состояние.
- Web `/login?next=%2Fsell`: `200`. Видимость CTA регистрации и раскрытие формы
  после гидратации браузера остаются **непроверенными**: CUA заблокировал переход
  на SSH-tunnel URL сообщением `Host access is restricted by policy.` Проверка
  строки в исходном HTML не засчитывается как browser acceptance. Source review
  подтвердил, что overlay кандидата не содержит login/auth/registration файлов.
- Свежий строгий HTTPS GET `https://suite-s1.denjik.by/compare` завершился до
  HTTP-ответа: `curl` exit `35`, HTTP `000`, TLS alert `unrecognized name`,
  remote IP `178.124.211.251`. Проверка TLS не отключалась. Nginx, DNS и TLS не
  менялись; доступность сайта снаружи по HTTPS не подтверждена.

## Влияние и ограничения

Выпуск заменил только API и web контейнеры. Проверки данных, изменений схемы,
миграций и внешнего browser acceptance не выполнялись. Для завершения принятия
UI регистрации требуется отдельная проверка гидратированной страницы входа в
браузере; внешний доступ по HTTPS ограничен текущим SNI/TLS сбоем.

## Уточнение canonical домена — 21 октября 2026

Пользователь уточнил, что рабочий домен портала — `https://авторынок.бел`, а
`suite-s1.denjik.by` является устаревшим адресом. Диагностика TLS выше относится
только к `suite-s1.denjik.by`; она не подтверждает недоступность портала на
canonical домене. Проверка canonical домена и браузерная приемка записаны в
`docs/runtime/CANONICAL_DOMAIN_ACCEPTANCE_2026-10-21.md`.
