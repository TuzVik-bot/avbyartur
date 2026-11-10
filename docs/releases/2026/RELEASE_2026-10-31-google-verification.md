# 31 октября 2026 — подтверждение Google

По запросу пользователя опубликован неизменённый `web/public/google92cb22c344dbd143.html`.
URL: https://xn--80aeylebmo7f.xn--90ais/google92cb22c344dbd143.html
Проверено HTTP 200 и побайтовое совпадение с оригиналом. Файл подтверждения Яндекса также сохранён и проверен HTTP 200.
SHA-256 Google: `b6847eb21f6b2d11bb1843590f8f1b3a98900dc573e7e8f91febfcfc712b2557`.

Production: `/home/suite/apps/releases/google-verification-20261031-r1`, активная ссылка `/home/suite/apps/avtorinok`.
Основа — копия действовавшего `yandex-verification-20261031-r1`; изменения только файл Google и compose override `docker-compose.google.yml` с образом `avtorinok-web:google-verification-20261031-r1`.
Compose project avtorinok; файлы docker-compose.yml, docker-compose.override.yml, docker-compose.public-launch.yml, docker-compose.feedback.yml, docker-compose.yandex.yml, docker-compose.google.yml.
API/worker и Nginx не менялись. Предыдущий web образ и исходники сохранены для отката. Главная, индексация и форма регистрации проверены после web-релиза.

Для отката web использовать предыдущий release yandex-verification-20261031-r1 и его пять compose-файлов (без google override), затем вернуть активную ссылку. Не удалять данные/тома.
