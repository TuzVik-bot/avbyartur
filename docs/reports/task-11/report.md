# Task 11 — скорость и доступность

Дата проверки: 15 октября 2026. Браузер: Chromium 147.0.7727.15. Все результаты — лабораторные измерения на localhost без throttling; это не field p75 и не проверка production.

## Изменения

- Кнопкам «Список» / «Сетка» задана минимальная высота 44 px, цвет выбранного пункта заменён на `var(--accent-dark)` для читаемого текста в обеих темах.
- Общий route-loading fallback получил минимальную высоту, которая удерживает footer ниже первого экрана на мобильной загрузке. Это устраняет скачок footer при замене fallback содержимым страницы.
- Для динамического текста `.filter-result-count` зарезервировано место: Playwright измерил высоту 36,39 px при ширине 360, 390 и 1440 px для состояний loading, ошибки, 0, 1 и 1 234 результата, а также общего пояснения. При узких размерах текст иногда занимает две строки, но блок сохраняет высоту. Данные последнего прохода: `/private/tmp/filter-count-reservation-evidence.json`.
- В существующих страницах карточек/объявлений размеров изображений и приоритета LCP-изображения не менял: detail уже помечает основное изображение приоритетным; изменение приоритета других картинок не подтверждалось измерениями.

## LCP: baseline → after, медиана мс

Условия обеих матриц одинаковые: 390×844 и 1440×900, DPR 1; по 3 запуска на страницу и cache mode. Cold — новый browser context на каждый запуск; warm — один прогревочный переход, затем три измеряемых перехода в том же context. Переход ждал `networkidle`, `document.fonts.ready` и 500 мс стабилизации.

| Страница | Mobile cold | Mobile warm | Desktop cold | Desktop warm |
|---|---:|---:|---:|---:|
| Главная | 212 → 224 | 200 → 208 | 228 → 212 | 200 → 200 |
| Каталог | 164 → 164 | 164 → 160 | 176 → 188 | 168 → 172 |
| Объявление | 160 → 172 | 148 → 160 | 172 → 176 | 152 → 160 |

Все медианы LCP ниже порога 2,5 с. Это synthetic local preview; результаты не предсказывают сетевые условия и пользовательский p75. Полные строки, медианы, браузер и конфигурация находятся в [before/measurements.json](before/measurements.json) и [after/measurements.json](after/measurements.json).

## CLS и исправление

В исходных 36 baseline-прогонах один mobile home cold sample имел CLS 0.4023; два соседних прогона — 0.00015. Дополнительное воспроизведение показало такой скачок в 1 из 8 cold заходов: до загрузки footer занимал y=507–844, а затем исчезал при замене loading fallback. Увеличил временную высоту fallback так, чтобы footer оставался ниже первого экрана.

После исправления все 36 матричных прогонов имели CLS не выше 0.000155. Восемь дополнительных mobile home cold прогонов также дали максимум 0.000155; большого скачка не было. Все after-медианы ниже целевого 0.05. По адресу события baseline видно, что причиной был footer при переходе с fallback; полевое поведение вне этого окружения здесь не измерялось.

## Адаптивность и доступность

- Каталог проверен на 360, 390, 768 и 1440 CSS px при preference `system`, `light`, `dark` — 12 сочетаний; горизонтальный overflow не найден.
- Для эффективной ширины 720 CSS px (эмуляция доступной ширины 1440 px при 200% zoom) overflow не найден. Это viewport-эмуляция, не управление zoom браузера.
- С включённым `prefers-reduced-motion: reduce` страница не переполняет viewport; `matchMedia` подтверждает заданную настройку.
- У выбранных «Список» / «Сетка» 44 px высоты; контраст текста после исправления — 7.46:1 в light и 6.71:1 в dark. До исправления выбранный пункт в dark был 2.43:1, высота кнопок — 38 px.
- Повторный проход геометрии фильтра проверил 360, 390 и 1440 px; высота блока счётчика оставалась 36,39 px при всех проверенных текстах. В этом проходе открытый вид шторки задавался существующим классом `is-open` в DOM вручную: повторно открыть её через UI не удалось из-за ошибки HMR/WebSocket в preview. Это подтверждает геометрию открытого вида, но не повторно подтверждает переход открытия в текущем preview.
- Переключение списка/сетки меняет `aria-pressed`. Мобильное меню и фильтр-шторка открываются и закрываются Escape; фокус возвращается на вызвавшую кнопку. Активные controls в каталоге получили accessible name.
- Подробная матрица и скриншоты: [after/accessibility.json](after/accessibility.json), `after/a11y-*.png`.

## Обязательные сценарии

Браузер проверялся с локальным mock API, без БД и без обращения к внешним сервисам. Mock-файл `/private/tmp/avbyartur_task11_api_fixture.py` расширен только для этого аудита и остаётся вне репозитория. Он возвращает `email_registration=true`, `email_registration_pilot=true`, отдельный test token для гостевого контакта и явные синтетические значения телефона/мессенджеров. Запуск локального mock: `python3.14 /private/tmp/avbyartur_task11_api_fixture.py`.

- `/login?next=%2Fsell`: mock capability включает UI «Создать аккаунт». Проверены поля имени, email, пароля и повтора, оба обязательных согласия и кнопка «Зарегистрироваться». Форму не отправлял; аккаунт не создавался.
- `/sell`: гость перенаправляется на `/login?next=%2Fsell`.
- Фильтр-шторка открывается, закрывается Escape и возвращает фокус.
- Сравнение сохраняет выбранное синтетическое объявление в localStorage и обновляет счётчик/действие.
- На detail mock-токен разрешает `phone-reveal`; UI показывает явно фиктивный телефон и ссылки Telegram/Viber. Это проверяет только браузерную интеграцию с локальной заглушкой — реальный backend, права доступа, данные контактов и реальные мессенджеры не проверялись.
- Сценарии с результатами и HTTP-статусами: [after/scenarios.json](after/scenarios.json); скриншоты — `after/scenario-*.png`.

## Проверки

- Полный `corepack pnpm test`: 579 passed, 1 failed, 99 files. Единственный сбой — `src/app/informational-pages.test.tsx` ждёт старую строку `Авторынок BY — закрытый пилот`; текущая about-страница уже содержит другое содержимое. Этот тест не связан с Task 11 и не менялся.
- Целевой `corepack pnpm exec vitest run src/components/catalog-display.test.tsx`: 2 passed.
- `corepack pnpm exec tsc --noEmit --incremental false`: passed. Стандартный `pnpm typecheck` не смог записать `web/tsconfig.tsbuildinfo` (EPERM) в worktree; вариант без incremental-файла проверил типы успешно.
- `git diff --check`: passed.

## Ограничения

Измерения не включают реальный браузерный трафик, полевые Web Vitals, production API, пользовательские сессии или действительные контактные данные. Регистрация проверена только по интерфейсу с локальной capability-заглушкой; отправку формы не выполнял.

## Fix round: reserve filter count space

After commit `9e0ad06` (`Reserve space for filter result count`), headless Playwright measured `.filter-result-count` at 360, 390, and 1440 CSS px. Generic/error fallback, loading, 0, 1, and 1,234 result copy all measured exactly 36.390625 px high at each width. Generic/error copy wrapped to two lines at 360 px and desktop; loading wrapped to two lines on desktop. The count block remained 36.390625 px throughout.

Command used to create and print `/private/tmp/filter-count-reservation-evidence.json`:

```sh
NODE_PATH=/Users/home/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules /Users/home/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node -e 'const{chromium}=require("playwright");const ss={generic:"Количество уточнится после применения фильтров",zero:"Найдено 0 предложений",one:"Найдено 1 предложение",many:"Найдено 1 234 предложения",loading:"Подбираем подходящие предложения",error:"Количество уточнится после применения фильтров"};(async()=>{const b=await chromium.launch({headless:true});const out=[];for(const width of [360,390,1440]){const p=await b.newPage({viewport:{width,height:900}});await p.goto("http://127.0.0.1:3003/cars",{waitUntil:"domcontentloaded"});await p.waitForTimeout(500);const data=await p.locator(".filter-result-count").evaluate((el,ss)=>{if(innerWidth<=800)el.closest(".filter-overlay").classList.add("is-open");const o={};for(const[k,t]of Object.entries(ss)){el.textContent=t;const n=el.firstChild,r=document.createRange();r.selectNodeContents(n);o[k]={height:el.getBoundingClientRect().height,width:el.getBoundingClientRect().width,lines:r.getClientRects().length,contentHeight:r.getBoundingClientRect().height,text:el.innerText}}return o},ss);out.push({width,states:data});await p.close()}require("fs").writeFileSync("/private/tmp/filter-count-reservation-evidence.json",JSON.stringify(out,null,2));console.log(JSON.stringify(out));await b.close()})().catch(e=>{console.error(e);process.exit(1)})'
```

The preview did not reopen the mobile drawer through the UI: the overlay remained `display: none`, and the preview reported an HMR/WebSocket handshake error. For the geometry measurement, the command manually applied the existing `.filter-overlay.is-open` class at mobile widths. This verifies layout in the open drawer state, not the UI transition that opens it.

`git diff --check` and `git diff --check HEAD^ HEAD` both exited 0 and produced no output.
