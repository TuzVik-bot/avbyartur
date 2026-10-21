# Trial: UX redesign from origin/main on top of production (integrate/20261022)

Optional trial branch for evaluation. Not for merging into integrate as is.

## Taken from origin/main (presentation)
- CSS layers: globals.css, home.module.css, new site-theme.css, home.css, catalog.css, auth.css, workspace.css, component CSS modules.
- Design assets web/public/design/*, Inter variable font (web/public/fonts), applied in layout.tsx (font, CSS imports, themeColor).
- Home page (page.tsx + test), home-search, site-header, site-footer (social icons), theme-switcher.
- Minor markup edits in account-nav, admin-nav, faq-topics, customs-calculator, dealers, login page.

## Kept from production (logic/data)
- All of backend/** (including alembic), docs, AGENTS/DEPLOYMENT/SERVER.
- web/src/lib/** (api, server-api, types, search-state, content), only i18n.ts got header.favorites / header.usefulInformation and "Компании".
- Layout providers (CompareProvider, contact consent, SiteAssistant, InstallPrompt), robots meta, global noindex in next.config.ts.
- Login form (registration flow), about, credit-policy, listing-card, search-filters, search-results, search-route, listing-detail, sell, moderation, account/*, currency-converter, vin-check, useful-information, informational-page, cars.

## Known gaps
- origin/main category pages (/trucks, /buses, ..., [category]/[...slug]), /financing and category-fields were dropped: they depend on backend/lib that production lacks.
- Catalog cards, filters, listing detail, sell form, about and login keep production markup; they get only the shared CSS/theme, so some class names from the new CSS may not match (visual polish needed).
- Header/footer nav entries for removed routes may need checking.
- Not visually verified in a browser; only typecheck, vitest and next build.

## Results
typecheck OK; vitest 115 files / 637 passed, 6 skipped (pre-existing); next build --webpack OK.

## Preview locally
    cd web && corepack pnpm install --frozen-lockfile
    API_BASE_URL=<api> API_INTERNAL_URL=<api> corepack pnpm dev
