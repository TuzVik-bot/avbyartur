# Главная, популярные марки и рекламные блоки — 24 октября 2026

## Активный release

- Canonical URL: `https://авторынок.бел/`.
- Read-only SSH показал `/home/suite/apps/avtorinok` →
  `/home/suite/apps/releases/homepage-ads-20261024-r1`.
- Активный web image: `avtorinok-web:homepage-ads-20261024-r1`, image ID
  `sha256:4c3e70de8fd4d7fd134d3a6fe4ec364681f63c08d8406f1073558880dcbc0c96`.
- До переключения точной task-specific базой был
  `/home/suite/apps/releases/footer-compact-20261024-r1`, image
  `avtorinok-web:footer-compact-20261024-r1`. Его `docker-compose.footer-release.yml`
  сохранён в активном каталоге и задаёт rollback web image. Общие
  `docker-compose.yml`, `docker-compose.override.yml`,
  `docker-compose.editorial-release.yml` и
  `docker-compose.moderation-release.yml` совпадают с footer-базой. Сетевое
  отображение сервиса web осталось `127.0.0.1:8080 -> 3000/tcp`.
- Общий `rollback-release.txt` нового каталога указывает на moderation release;
  для отката этой задачи следует использовать сохранённую footer-базу и
  `footer-compact-20261024-r1`, чтобы сохранить её изменения.

## Внутренние проверки

Read-only HTTP к активному web на `127.0.0.1:8080` с Host canonical вернул
`200` для `/` и `/login?next=%2Fsell`.

- Главная отдала заголовок «Автомобили Беларуси» и строки рекламных блоков
  «Реклама», «Разместить рекламу» и «Подать объявление».
- Login SSR отдал email- и password-поля. Все 10 JS chunks загрузились; в них
  найдены строки «Создать аккаунт», «Зарегистрироваться» и «Повторите пароль».
- Это проверка ответа приложения и наличия UI-кода в bundle. Hydrated-форма в
  браузере, её чекбоксы и отправка не проверялись.
- На последнем наблюдённом `docker ps` все пять сервисов были healthy. В том
  snapshot API и worker недавно перезапускались; их состояние после этого
  подтверждено как healthy, но я не устанавливал причину рестарта.

## Публичная приемка и ограничения

Публичный browser gate не закрыт. В этой сессии CUA заблокировал доступ к Chrome
политикой host access, а web browser tool не открыл canonical URL. Локальная
попытка `curl` без закрепления адреса не разрешила DNS. DNS lookup на VPS
разрешился в `178.124.211.251`; HTTPS curl с `--resolve` не установил TCP
соединение. На VPS в момент проверки слушали `127.0.0.1:8080` и HTTP-порт `80`;
локального listener на `443` не было. Эти источники не подтвердили внешний TLS
сертификат, публичные HTTP-заголовки, отсутствие Basic Auth или актуальный
`X-Robots-Tag`. Старые runtime-отчёты относятся к предыдущей проверке и не
заменяют acceptance текущего release.

Публичные URLs для ручной проверки:

- [Главная](https://авторынок.бел/)
- [Вход и регистрация](https://авторынок.бел/login?next=%2Fsell)

Тома, Nginx и TLS/DNS конфигурация во время этих проверок не менялись.
