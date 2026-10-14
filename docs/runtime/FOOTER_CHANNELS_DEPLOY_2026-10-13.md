# Значки соцсетей и магазинов приложений — 13 октября 2026

- GitHub main: `ac34ff2`, отдельный коммит только трёх файлов подвала.
- VPS release: `/home/suite/apps/releases/footer-channels-20261013`.
- Web image: `avtorinok-web:footer-channels-20261013`, linux/amd64.
- Rollback release: `/home/suite/apps/releases/catalog-search-20261010T131523Z-3e296e0`.
- Rollback web image: `avtorinok-web:catalog-search-20261010T131523Z-3e296e0`.

Новый релиз создан из текущего VPS-кода. Добавлены компоненты
`footer-channels.tsx`, `footer-channels.module.css` и две строки интеграции
в действующий подвал. Telegram, Instagram, VK, YouTube, Google Play и
App Store имеют пустые URL и отображаются неактивными. Магазины отмечены
«Скоро в». Остальные локальные незавершённые изменения не включены.

## Проверки

- Локальные тесты существующего подвала: 2 passed; TypeScript: passed.
- Production Docker build на VPS: passed, web healthy.
- Публичный HTTPS с Mac: HTTP/2 200, `noindex, nofollow, noarchive`
  сохранён. Обращение с самого VPS к публичному порту 443 не прошло;
  внешние проверки curl и браузера успешны.
- ID, образы и mount конфигурация API, worker, DB и test-mail до/после
  полностью совпали. Именованные тома сохранены.
- Контрольные суммы `.env`, Compose, формы входа и API-клиента совпали;
  права `.env` — 600.
- На реальном HTTPS-домене в браузере присутствуют шесть неактивных элементов
  без href; значки и кнопки визуально проверены.
- На ширине 390 px все шесть элементов помещаются; горизонтального
  переполнения документа не обнаружено.
- `/login?next=%2Fsell`: кнопка «Создать аккаунт» открывает имя, email,
  пароль, повтор пароля, два согласия и «Зарегистрироваться».
  Регистрация нового аккаунта не выполнялась.

Скриншоты: `footer-channels-live-2026-10-13.jpg`,
`footer-channels-mobile-2026-10-13.jpg`.

## Откат только web

Из нового release выполнить Compose с временным override, закрепляющим
`services.web.image` на rollback web image, и `up -d --no-deps --no-build
--wait web`. Затем вернуть `/home/suite/apps/avtorinok` на rollback release.
Это сохраняет исходный release и не меняет остальные контейнеры. Не выполнять
автоматический откат БД или удаление томов. Откат не выполнялся.
