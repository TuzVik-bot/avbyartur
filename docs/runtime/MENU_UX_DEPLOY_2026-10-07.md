# Релиз меню — 7 октября 2026

Выпуск: `/home/suite/apps/releases/menu-ux-20261007T1405Z`.
Образ: `avtorinok-web:menu-ux-20261007T1405Z`.
Rollback: `/home/suite/apps/releases/registration-ui-fix-20261007` и прежний web-образ сохранены.

Новый выпуск скопирован из действующего VPS-релиза, заменены только `site-header.tsx`, `catalog-navigation.tsx`, `site-navigation.module.css`. Серверная Docker-сборка с TypeScript завершилась успешно. Compose config валиден; переключён только web через `up -d --no-deps web`, symlink `avtorinok` обновлён.

После переключения web healthy. Идентификаторы контейнеров API, worker и DB совпали с предрелизными. `.env` имеет права 600, SHA256 совпадает до/после. Именованные тома сохранены. API/DB без опубликованных портов. Nginx сохраняет `auth_basic off`, HTTPS возвращает 200 и `noindex, nofollow, noarchive`.

Браузерная проверка реального `/login?next=%2Fsell`: каталог раскрывается, Escape закрывает его; мобильная ширина 375 px без горизонтального переполнения. Кнопка «Создать аккаунт» присутствует, раскрывает имя/email/пароль/повтор/согласия/«Зарегистрироваться». Учётная запись не создавалась.

HTTPS smoke `/tires`, `/trucks`, `/currency-converter`: 200.
Скриншоты: `menu-production-desktop-2026-10-07.jpg`, `menu-production-mobile-2026-10-07.jpg`, `menu-production-registration-2026-10-07.jpg`.

Для отката приложений: из rollback-каталога выполнить `docker compose -p avtorinok up -d --no-deps web`, затем вернуть symlink. Откат не выполнялся. Данные/миграции не изменялись.
