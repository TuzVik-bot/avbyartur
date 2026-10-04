# Архив старого сайта FORTEBIT

Создан 26 сентября 2026 г. на VPS `suite@178.124.211.251:23026`.

Каталог: `/home/suite/backups/online-shop-retirement-20260926-190522`.
Архив содержит секреты конфигурации и данные старого магазина. Не публиковать,
не помещать в Git или корень сайта. Права каталога — 700, файлов — 600.

## Состав

- `site-files.tar.gz`: `/home/suite/apps/ONLINE-SHOP` и `ONLINE-SHOP-old-20260728`,
  включая исходники, Git и конфигурацию.
- `postgres-current.sql.gz`: логический дамп PostgreSQL перед остановкой.
- `pgdata-volume.tar.gz`: файловая копия тома PostgreSQL после остановки.
- `meili-volume.tar.gz`, `minio-volume.tar.gz`: остановленные тома поиска и хранилища.
- `caddy-config-volume.tar.gz`, `caddy-data-volume.tar.gz`: тома старого веб-сервера.
- `home-retirement-artifacts.tar.gz`: предыдущие env-копии, скрипт резервирования,
  старый дамп, журналы и служебные каталоги развёртывания.
- `SHA256SUMS`: контрольные суммы семи файлов `.tar.gz` и одного `.sql.gz`.

Прежние ежедневные дампы в `/home/suite/backups` и более ранняя копия
`/home/suite/ONLINE-SHOP-backup-20260728` также сохранены.

## Что удалено из рабочего окружения

Compose-проект `online-shop`: шесть контейнеров, пять томов, сеть, образы и кэш
сборки. Активные исходники удалены из `/home/suite/apps/ONLINE-SHOP`.
Задание cron `15 3 * * * /home/suite/backup-db.sh >> /home/suite/logs/backup.log 2>&1`
удалено; соответствующий скрипт хранится в архиве.

## Восстановление — только при отдельном решении

Полное тестовое восстановление не проводилось. Проверены SHA-256, целостность
gzip, чтение оглавлений tar и наличие завершающего маркера логического дампа.

Для восстановления сначала проверить `sha256sum -c SHA256SUMS` в каталоге архива.
Во время согласованного окна остановить Nginx, вернуть исходники на прежний путь,
восстановить владельца `suite:suite`, создать исходные Docker-тома и распаковать
каждый соответствующий архив в корень своего тома с сохранением UID/GID.
Для файлового тома БД использовать PostgreSQL 16.

Исходные тома: `online-shop_pgdata`, `online-shop_meili`, `online-shop_minio`,
`online-shop_caddy_config`, `online-shop_caddy_data`.

Compose-файлы: `docker-compose.prod.yml` и `docker-compose.single-http.yml`.
Прежние образы: `postgres:16-alpine`, `getmeili/meilisearch:v1.11`,
`minio/minio:RELEASE.2023-03-20T20-16-18Z`, `caddy:2.9-alpine`.
Образы web/API необходимо пересобрать из исходников. Восстановление затронет
новый сайт и порт 80; автоматически не запускать.
