# Complete Avtorinok UX redesign
Approved by user 2026-10-04. Goal: modern light automotive marketplace for buying and selling; all public, account, moderation and admin routes included.
## Constraints
Keep existing routes, query parameters, API, business validation and role gates. No backend migration, VPS changes, production/demo imports, new tracking, commercial promises or altered legal text. Keep noindex and current pilot capability gates. Brand/cornflower remain. Palette #F6F7F9 / #FFFFFF / #18212F / #3F5CC4 / #E2E6ED. Inter Cyrillic self-hosted, 16px base, 8px spacing, 12px cards. Keep all six sell steps, autosave, photo validation, revision handling and secure contacts.
## Task 1: Assets
Root owns nine generated images + originals in web/public/design: hero-desktop 1600x1000, hero-mobile 900x1200, sell/dealers/customs/about 1200x800, empty-search/empty-favorites/empty-messages 800x800. WebP budgets 250KB hero desktop, 150KB mobile, 120KB others. Photo-led pale architecture, natural shadows, blue highlights, no baked text/brands/claims. Asset manifest + alt text. Never use generated photos as listing photos. Root also owns local QA runtime and reports.
## Task 2: Full application redesign
Implementer owns web/src, web/public/fonts and font licenses; may update web config/scripts/tests if needed, but not generated design assets. Use existing Next 16.3 React19 APIs/docs and lucide. Separate screen-specific styles from global foundations. Home hero exact heading "Найдите свой автомобиль в Беларуси", search make/model/price_max backed by real catalog and URL; content sequence search,new listings,query-based collections,seller benefits,3 sale steps,dealers,customs. Honest makes label; no fake popularity/counts/data. Empty catalogue CTA sell; query-no-results reset only when conditions present. Search primary make/model/price/year/region; advanced grouped collapsed; accessible mobile dialog apply/reset, Escape and focus restore. Listing/detail use only actual photo_urls/cover_url, else neutral Photo not added. Strong price/specs/seller gallery/contact actions, mobile contact area. Public dealers/customs/info consistent with factual copy; sale asset reused login. Auth explains pilot and next destination, respects existing phone/email capabilities. Cabinet desktop side nav/mobile compact; all existing sections including billing/company/team/feeds/analytics/messages. Sell named 6-step navigation and autosave status, no business change. Moderation/readable queues/actions/risk reasons. All admin sections dashboard/users/audit/catalog/requests/settings/tariffs/content/monitoring use cohesive accessible data UI; scoped table overflow, text+color statuses, preserve security confirmations.
TDD for new behavior, proportionate checks for CSS. Test make-model dependency loading/errors/stale responses/query, mobile panel keyboard focus/reset, no-photo fallback, empty vs filtered, safe return after auth. Run pnpm test/typecheck/build. No dependency churn.
### Task 2 implementation report — 2026-10-05

**Status:** source implementation and the reviewed fix wave are complete and frozen for root browser QA and final review. Route-level visual matrix and end-to-end acceptance remain pending; no deployment was performed.

**Reviewed fixes included:**

- Staff header navigation collapses above 1200 px while retaining its accessible toggle and routes.
- Removed the 320 px minimum width from the document root so narrow viewports can reflow.
- Replaced the unsupported phone-display promise with the approved factual copy, `Контакты не показываются в публичной выдаче`; the home catalog label is the approved `Марки автомобилей`.
- Typed and passed the nullable listing-search `fx` response through server and client APIs to the home search. The BYN maximum-price field stays disabled with an explanation until `fx` is confirmed; missing/null `fx` and a rejected initial listings request both fail closed.
- Existing listing phone-reveal and chat actions are fixed at the bottom on mobile, with safe-area padding and room in the page flow.
- Account and admin navigation stays on one horizontally scrollable row on mobile, with the current route first.
- Company analytics and moderation queue statuses use localized text badges while retaining wire values.
- Cookie-policy tables keep all columns in a width-constrained horizontal scroll region at narrow sizes; long inline technical names wrap without changing their text.

**Verification:**

- Web tests on the final source: `corepack pnpm test` — 78 files, 443 tests passed. The focused home-page regression file passed `corepack pnpm exec vitest run src/app/page.test.tsx` — 1 file, 7 tests, including the rejected initial listings request.
- TypeScript: `corepack pnpm typecheck` passed after the final copy edit.
- Production build: `corepack pnpm exec next build --webpack` passed and enumerated all App Router routes. The default `corepack pnpm build` was blocked by Turbopack rejecting the managed worktree's `web/node_modules` symlink to `/Users/home/Downloads/avbyartur/web/node_modules` as outside its filesystem root; the webpack build verified the same source successfully.
- `git diff --check` passed.
- Root reports the isolated local API returned `/health/ready` 200 on port 8016, with 7 API and 6 lifecycle scenarios passing against the separate PostgreSQL instance on port 55564. This is root-provided local QA evidence, not a VPS or production check.
- Root browser matrix, screenshots, and final visual review are still pending.

**Exact changed scope:**

- App routes and shell: `web/src/app/about/page.tsx`; `web/src/app/account/company/analytics/page.tsx`, `page.test.tsx`; `web/src/app/account/favorites/page.tsx`; `web/src/app/account/listings/page.tsx`; `web/src/app/dealers/page.tsx`; `web/src/app/globals.css`; `web/src/app/layout.tsx`, `layout.test.tsx`; `web/src/app/login/page.tsx`; `web/src/app/moderation/page.tsx`; `web/src/app/page.tsx`, `page.test.tsx`; `web/src/app/sell/page.tsx`; and new `web/src/app/auth.css`, `catalog.css`, `home.css`, `workspace.css`.
- Components: `web/src/components/account-nav.tsx`; `admin-nav.tsx`; `admin-tariff-editor.module.css`; `conversation-inbox.tsx`; `customs-calculator.module.css`, `customs-calculator.tsx`; `informational-page.tsx`; `listing-card.tsx`, `listing-card.test.tsx`; `listing-detail.tsx`, `listing-detail.test.tsx`; `login-form.tsx`, `login-form.test.tsx`; `moderation-page.test.tsx`; `search-filters.tsx`, `search-filters.test.tsx`; `search-results.tsx`, `search-results.test.tsx`; `search-route.tsx`; `sell-form.tsx`, `sell-form.test.tsx`; `site-header.tsx`, `site-header.test.tsx`; and new `home-search.tsx`, `home-search.test.tsx`.
- API contracts: `web/src/lib/api.ts`, `server-api.ts`, `types.ts`, plus new `web/src/lib/status-presentation.ts`.
- Design assets: `web/public/design/README.md`, `manifest.json`; WebP `about`, `customs`, `dealers`, `empty-favorites`, `empty-messages`, `empty-search`, `hero-desktop`, `hero-mobile`, and `sell`; matching nine PNG originals under `web/public/design/originals/`.
- Font: `web/public/fonts/Inter-Variable.ttf` and its `OFL.txt` license.
- Plan/report: `docs/superpowers/plans/2026-10-04-ux-redesign.md`.

## Task 3: Verification
Root sets isolated LOCAL backend/DB or safe deterministic fixture server for visual states; never connects new preview to VPS/tunnel. Fresh anonymous baseline screenshots already exist /private/tmp/avtorinok-ux-audit-20261004. Browse through CUA iab; check ALL routes at390/768/1440, reflow320, keyboard/motion/focus/errors/loading/empty/filled. Exercise real local end-to-end flow buy/contact; login/six steps/moderation; messages/favorites/settings/admin. If real backend cannot be established, clearly label fixtures and unverified end-to-end limitations. Save screenshots, no personal credentials in outputs. Review implementation and fix findings before completion. Local preview is deliverable, deploy separate authority.
