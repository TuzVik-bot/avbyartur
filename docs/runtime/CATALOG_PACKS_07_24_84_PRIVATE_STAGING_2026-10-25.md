# Пакеты каталога 07.24–07.84 — приватный staging — 25 октября 2026

## Содержимое и статус

Архив содержит модели транспорта и характеристики, а не объявления о продаже:
нет цен, фотографий или данных продавцов. Включены лодки, мотоциклы и другие
категории техники.

- SHA-256 ZIP: `ee89f0da38ef2f09ecf88e7817f4dc0e384db9650d392558a8944af9f1b49c44`.
- 61 оригинальный ZIP (07.24–07.84), 1 099 consolidated model rows,
  8 320 spec rows, 836 variant rows, 1 109 source/rights rows.
- В ZIP нет небезопасных путей/симлинков; CRC прошёл. CRC и SHA-256 для всех
  61 вложенных ZIP совпали с `reports/checked_archives.csv`.
- 4 225 строк `05_cumulative_registry.csv` сохранены как historical reference;
  повторно как incremental source они не импортировались.
- 241 группы характеристик имеют конфликтующие значения/квалификаторы.
  README указывает, что коммерческая лицензия не получена. Статусы источника
  `needs_rights_clearance`, crosscheck `needs_crosscheck`; автоматический
  model year не заполнялся. Все данные остаются в `HOLD`.

## Перекрытия с уже учтёнными пакетами

SHA-256 оригинальных пакетов 07.24–07.27 точно совпали с hashes в прежних
receipt; их сырые строки сохранены для provenance, но исключены из incremental
счётчиков:

| Источник | Receipt | Models | Specs | Variants | Rights |
| --- | --- | ---: | ---: | ---: | ---: |
| 07.24 и 07.27 | `17390ba9-134f-404a-a230-ad7a04e823c9` | 57 | 273 | 26 | 57 |
| 07.25 и 07.26 | `5cc0fc98-87ac-4188-ae31-18db386e5096` | 132 | 394 | 64 | 132 |
| **Всего overlap** |  | **189** | **667** | **90** | **189** |

Новые private review rows: **910 models, 7 653 specs, 746 variants, 920
source/rights rows**. Rejected rows: 0. Конфликтующие данные не публиковались.

## Импорт и видимость

Вставлена одна запись `catalog_imports` с полным consolidated payload,
manifest, per-pack hashes, конфликтами, QA notes и приватными review statuses:

- Receipt: `1b641dce-d269-449f-82a1-1fc3fea3b7eb`.
- Checksum: `ee89f0da38ef2f09ecf88e7817f4dc0e384db9650d392558a8944af9f1b49c44`.
- Metadata: `status=review_only`, `visibility=private_staging_only`,
  publication `HOLD: needs_crosscheck + needs_rights_clearance`.
- Использован advisory lock `74101501`; повторный запуск с тем же ZIP SHA
  вернул `unchanged` и тот же receipt ID.
- Количество receipts: 26 → 27. `catalog_makes`, `catalog_models`,
  `catalog_generations`, `catalog_body_types`, `catalog_body_variants`,
  `catalog_sources` и `catalog_modifications` не изменились.

До и после insert counts совпали: makes 232, models 4 538, generations
14 009, body types 9, body variants 13 273, sources 1, modifications 194 817.
Таким образом публичный каталог не получил новые строки; staging payload
сохранён только в import receipt. Публичный API sample lookup после insert не
выполнялся.

## Backup и сохранность

- Исходный ZIP хранится на сервере: `/home/suite/backups/avtorinok/catalog-unified-07-24-84-20261025T1005Z/source.zip`.
  Каталог mode `700`, файл mode `600`; SHA-256 совпадает с локальным архивом.
- Pre-import PostgreSQL custom dump: `/home/suite/backups/avtorinok/catalog-unified-07-24-84-20261025T1005Z/pre-import.dump`, mode `600`, SHA-256
  `c45b3c41126c175b0265cb821f2aa92bf46b1f17da5c92699ca98575363d7165`.
  `pg_restore --list` в DB container прочитал 542 TOC entries.
- Проверка до insert подтвердила active release
  `/home/suite/apps/releases/homepage-ads-20261024-r1`, `.env` mode `600`,
  PostgreSQL volume `avtorinok_postgres`; `X-Robots-Tag` был
  `noindex, nofollow, noarchive`. Код приложения, Nginx, `.env` и volumes
  для staging не менялись.
- Загрузка ZIP и helper во временный API-container directory mode `700`, UID
  `10001`, завершена; временная копия удалена после вставки. Host ZIP, dump,
  helper и receipt сохранены.
