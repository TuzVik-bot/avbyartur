# 31 октября 2026 — файл подтверждения Яндекса

По запросу пользователя опубликован неизменённый файл `web/public/yandex_8cebfb4be81fa555.html`.
Публичный URL: https://xn--80aeylebmo7f.xn--90ais/yandex_8cebfb4be81fa555.html
Проверено HTTP 200, text/html; charset=UTF-8, побайтовое совпадение с оригиналом.
SHA-256: `97aa640b012f71ec6a42b6c91f49763a6e9e4f893c3b3b637a989acf34031f08`.

Текущая серверная версия: `/home/suite/apps/releases/yandex-verification-20261031-r1`, ссылка `/home/suite/apps/avtorinok`.
Основа: точная копия предыдущего `feedback-20261030-r1`. Изменены только файл подтверждения и новый compose override `docker-compose.yandex.yml` с образом web `avtorinok-web:yandex-verification-20261031-r1`. API/worker не обновлялись, их предыдущие флаги сохранены.
Compose files: docker-compose.yml, docker-compose.override.yml, docker-compose.public-launch.yml, docker-compose.feedback.yml, docker-compose.yandex.yml; project avtorinok.
Web образ собран на сервере, контейнер healthy. Главная и регистрация проверены отдельно в браузере. Индексация `index, follow` сохранена. Nginx не менялся.

Этот HTML — подтверждение владения сайтом. Новый JavaScript-счётчик Метрики в рамках этой задачи не устанавливался.

Откат web: из `/home/suite/apps/releases/feedback-20261030-r1` выполнить `docker compose -p avtorinok -f docker-compose.yml -f docker-compose.override.yml -f docker-compose.public-launch.yml -f docker-compose.feedback.yml up -d --no-deps --no-build --wait web`, затем вернуть активную ссылку на этот каталог. Данные и тома не удалять.
