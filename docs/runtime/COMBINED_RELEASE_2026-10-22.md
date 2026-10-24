# Combined web release — 22 October 2026

## Release

Activated web release `product-wave-articles-20261022-r1` at
`/home/suite/apps/releases/product-wave-articles-20261022-r1`, using image
`avtorinok-web:product-wave-articles-20261022-r1`. The Next.js production build
and TypeScript check passed. A GET-only candidate smoke opened the article list
and the guide about preparing a car for sale.

The database dump was taken under
`/home/suite/apps/avtorinok-web-deploy.lock` before the web switch:

- Snapshot: `/home/suite/backups/avtorinok/pre-web-product-wave-articles-20261021T214414Z/`
- SHA-256: `56c03ee7e966294157fe2f1d118f92a1bbba63141e3d8907b1b5f2388731f6a4`
- `pg_restore --list`: passed, 527 TOC entries.

The new web container became healthy. API, worker, database, and named volumes
were left on their existing runtime. The host `.env` remained mode `600`; its
hash was unchanged. No database migration or listing import was part of this
release.

## Canonical HTTPS browser smoke

Checked in the browser on `https://xn--80aeylebmo7f.xn--90ais` on 22 October
2026. The HTTPS pages loaded without a certificate interstitial.

- `/login?next=%2Fsell`: after selecting **Создать аккаунт**, the hydrated
  page showed **Имя**, **Электронная почта**, **Пароль**, and **Повторите
  пароль** fields; both consent checkboxes and links to `/registration-terms`
  and `/registration-privacy`; and the **Зарегистрироваться** button. The
  test-mode notices were visible. No fields were filled and the form was not
  submitted.
- `/useful-information/articles`: the heading **Статьи и инструкции** and all
  three article cards were visible. The seller guide link opened the detail
  page below.
- `/useful-information/articles/podgotovka-avtomobilya-k-prodazhe`: the title
  **Как подготовить автомобиль и объявление к продаже** and byline
  **Редакционный материал · Обновлено 22 октября 2026** were visible. The
  article's **Открыть объявления с пробегом** link and **Создать объявление**
  CTA were present; the CTA targets `/sell`.

## Rollback and acceptance boundary

The immediate previous release remains at
`/home/suite/apps/releases/product-wave-20261021-r1`. Read-only inspection
confirmed the retained rollback image `avtorinok-web:product-wave-20261021-r1`
with image ID
`sha256:2281b06bc73dc28b516567f74bb047360fd3b411f00448b1376f33a7487051d7`.
No rollback was performed. If needed, restore the previous release for the web
service only; keep API, worker, database, and named volumes on their current
runtime.

The pre-release check recorded **0 active listings**. A post-release recount was
not performed. This smoke therefore accepts the checked web routes and
registration UI only; it does not establish an active listing journey. No
synthetic listing was created.
