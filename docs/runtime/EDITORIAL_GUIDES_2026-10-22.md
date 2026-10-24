# Editorial guides — 22 October 2026

## Scope

Extended the existing static article package at `/useful-information/articles` using the three Russian drafts in `docs/content/first-articles-ru.md`. The pages cover buying a used car, preparing a car for sale, and selecting an auto service. The existing useful-information landing page already renders the article cards and four editable search presets, so no separate `/guides` or `/collections` route was added.

Each detail page now identifies the text as an editorial material and shows its update date. It also offers next steps tied to the article: the buyer guide links to the existing preset anchor and used-car search, the seller guide links to used-car search and `/sell`, and the service guide links to `/services`. The search URL uses the same existing query parameters as the preset cards. No individual author credentials, reviews, vehicle-specific claims, or legal guarantees were added.

## Local verification

- `corepack pnpm typecheck` in `web/` — passed before the final seller CTA copy correction.
- `corepack pnpm test -- src/app/useful-information/articles/page.test.tsx` — passed before the final seller CTA copy correction: Vitest reported 101 test files and 580 tests.
- After the final copy correction, `corepack pnpm exec vitest run src/app/useful-information/articles/page.test.tsx` passed: 1 file, 6 tests.
- The targeted article tests cover editorial ownership/date, rendered next-step links, the existing preset anchor, used-car search parameters, seller route, and services route.

## Release boundary

This report records local source and test evidence only. No deployment was performed by this package owner, and the public site/browser was not checked for these article changes. Production availability and live route acceptance must be confirmed against the release root coordinates.
