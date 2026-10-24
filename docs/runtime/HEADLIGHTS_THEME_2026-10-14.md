# Переключатель цвета сайта в виде фар — 14 октября 2026

Вместо меню темы — кнопка с автомобильной фарой и подписью «Цвет сайта». Одно нажатие переключает светлый/тёмный режим. Лучи подсвечиваются при тёмном оформлении. Выбор хранится в localStorage; до первого явного выбора сохраняется следование системной теме и синхронизация вкладок. У кнопки есть описательный aria-label, aria-pressed и native keyboard activation.

Код отправлен в main: `9c8960e`, `d1a00f4`, `025ef73`. Минимальные зависимости и подключение к шапке сохранены в Git отдельно от незакоммиченного рабочего дерева.

Локально: 12 тестов переключателя/шапки PASS, TypeScript PASS. Отдельная копия main: 11 тестов PASS, TypeScript PASS. Браузер: обе темы, сохранение после reload; 390 и 320 px без горизонтального переполнения.

Деплой: скопирован актуальный `/home/suite/apps/releases/all-makes-20261014-85085da`; заменены только `theme-switcher.tsx` и `theme-switcher.module.css`. Кандидат `/home/suite/apps/releases/headlights-20261014-r3`. Production Docker build включает проверку TypeScript. API, worker и данные не обновляются этим релизом. `.env` остаётся mode600, без изменения содержимого. Предрелизные состояния сохранены на VPS в `home-deploy-before.json`.

Откат web: из `/home/suite/apps/releases/all-makes-20261014-85085da` выполнить `docker compose -p avtorinok up -d --no-deps --no-build --wait web`, затем атомарно вернуть symlink `/home/suite/apps/avtorinok` на этот каталог. Не удалять тома и не понижать БД.

Финальная проверка: web `sha256:c4847d2b057cd626a1d8748397b6bac60163326ba3cc65b6b8ec7022dbb0907f` healthy; HTTPS200/noindex сохранён. API/worker/DB/test-mail ID и mounts сохранены (mounts сравниваются по Destination, поскольку Docker может менять порядок). Реальный браузер подтвердил включённые фары, оба направления переключения и сохранение тёмной темы после reload. Финальные desktop1280/mobile390 без горизонтального переполнения.
