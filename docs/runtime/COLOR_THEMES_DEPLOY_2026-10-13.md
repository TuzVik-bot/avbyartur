# Темы оформления — релиз 13 октября 2026

- Сайт: https://suite-s1.denjik.by/
- Git: `codex/color-themes-20261013`, frontend commit `47849cbed9e5e1826472b283784b66bc5a54335e`.
- Релиз VPS: `/home/suite/apps/releases/color-themes-20261013`.
- Web image: `avtorinok-web:color-themes-20261013`.
- Rollback: `/home/suite/apps/releases/footer-channels-20261013`; прежний web image сохранён.

В отдельной ветке сохранён frontend действующего VPS-релиза, затем добавлены темы. Исходный локальный checkout с незакоммиченными изменениями не переключался и не очищался. Релиз скопирован из действующего VPS-каталога; наложены только 14 frontend-файлов. Светлая палитра действующего сайта сохранена. Секреты не передавались в Git.

Проверки: 94 web test files / 585 tests PASS, TypeScript PASS, production AMD64 Docker build PASS. После переключения только web: healthy, HTTPS 200, noindex сохранён, общий Basic Auth выключен. `.env` hash/mode 600 совпадают; ID/образы/mounts API, worker и DB совпали с предрелизными. Миграции и импорт не выполнялись.

Реальный браузер: меню «Светлая / Тёмная / Системная», переключение всех режимов, сохранённая тёмная тема после reload, мобильная ширина 320 px без переполнения. На `/login?next=%2Fsell` открыты «Создать аккаунт», имя/email/пароль/повтор/оба согласия/«Зарегистрироваться»; аккаунт не создавался. Автоматическое следование изменениям системной темы проверено тестами; настройки ОС через браузер не менялись.

Откат web: из `/home/suite/apps/releases/footer-channels-20261013` выполнить `docker compose -p avtorinok up -d --no-deps --no-build --wait web`, затем атомарно вернуть symlink `/home/suite/apps/avtorinok` на этот каталог. Не откатывать БД и не удалять тома. Откат не запускался.

Предрелизная квитанция на VPS: `theme-pre-deploy.json`. Скриншот в исходном workspace: `docs/runtime/theme-production-2026-10-13.png`.
