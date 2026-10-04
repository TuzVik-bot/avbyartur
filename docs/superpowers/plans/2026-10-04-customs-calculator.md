# Customs Calculator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement task-by-task. User explicitly selected GPT-6 Luna, reasoning max, for all agents.

**Goal:** Добавить собственный таможенный калькулятор первого сценария с проверяемыми ставками, официальными курсами и честным барьером публикации.

**Architecture:** Python Decimal ядро + версия ставок JSON + изолированный клиент НБРБ + FastAPI read-only endpoints. Next.js форма получает только серверный расчет и отображает юридические источники и дату курса.

**Tech Stack:** FastAPI/Pydantic, Python 3.12/Decimal/urllib, Next.js 16/React 19/TypeScript/Vitest.

**Spec:** docs/superpowers/specs/2026-10-04-customs-calculator-design.md

## Global Constraints
- Первая версия: физлицо, личное пользование, M1 бензин/дизель из-за пределов ЕАЭС в Беларусь без льгот.
- EV, гибриды, ЕАЭС, юрлица и льготы не рассчитываются.
- Decimal; календарные годовщины; пороги до округления; HALF_UP до 0.01; итог равен сумме строк.
- Действующие юридические ставки имеют источник и effective_from/effective_to; нет подтвержденной нормы — нет расчета.
- Публичные суммы доступны только после реальной сверки ГТК, статус связан с версией правил.
- Курсы только НБРБ на дату Europe/Minsk, Cur_OfficialRate / Cur_Scale, никаких stale fallback.
- В Git не включать локальные ссылки backend/.venv и web/node_modules, секреты, ENV/runtime данные.
- Не изменять VPS, production БД, named volumes, Basic Auth/noindex; не использовать integration fixture без disposable БД.
- Рабочее дерево /Users/home/.codex/worktrees/customs-calculator/avbyartur; остальные участники работают рядом, не откатывать чужие изменения; не запускать дочерних агентов.

## Task 1: Backend rules, engine, rates and API
**Ownership / Files:** Create backend/app/customs_calculator.py, backend/app/customs_rates.py, backend/app/customs_schemas.py, backend/app/api/customs_calculator.py, backend/app/data/customs-rules.json; modify backend/app/main.py only to register router and error contract. Create backend/tests/test_customs_calculator.py, test_customs_rates.py, test_customs_api.py. Researcher separately owns docs/customs/*; read its report before adding legal values. No frontend edits.
**Interfaces:** Produces the exact GET/POST and request/response field names listed in Spec. GET works without rates/DB, public POST is gated by actual verified legal/control status. Pure calculate service accepts injected calculation_date and rate snapshot for deterministic tests. Report resolved schema details to controller before Task 2.
- [ ] Read Spec, relevant existing error/OpenAPI patterns, official research. Raise missing verified inputs; do not invent.
- [ ] Write failing tests: all duty price/volume bands, anniversaries 3/5 including leap year, percent vs minimum, high precision near EUR thresholds, money rounding, unsupported scenario/date/value.
- [ ] Run tests RED using existing backend/.venv Python; no integration fixture/DB connection.
- [ ] Implement JSON validated versions, Decimal engine, source provenance and release control.
- [ ] Write failing transport tests for EUR/USD/BYN/RUB/CNY, scales 100/10, mismatched dates/currencies, nonfinite/zero, missing EUR, timeout, size limit and bounded concurrency/cache.
- [ ] Implement fixed-host NBRB fetcher, safe cache, no stale fallback, FastAPI GET/POST and ApiErrorOut contract.
- [ ] Run focused tests GREEN, backend OpenAPI and error-contract regression tests without integration; inspect diff and commit only owned files. Report RED/GREEN commands and limitations to .superpowers/sdd/customs-calculator/backend-report.md.

## Task 2: Website form, navigation and typed contract
**Ownership / Files:** Create web/src/app/customs-calculator/page.tsx, web/src/components/customs-calculator.tsx, scoped CSS module (or page stylesheet), web/src/components/customs-calculator.test.tsx, web/src/lib/customs-calculator.ts; modify web/src/components/site-header.tsx, site-footer.tsx, web/src/lib/i18n.ts and relevant navigation tests; generate web/src/lib/types.generated.ts. No backend edits. Existing generic API request helper may be exported minimally if needed, use ApiClientError envelope.
**Interfaces:** Consumes Task 1 OpenAPI schemas and endpoints exactly. No client legal arithmetic; render exact server amounts, rate_date/sources/warnings. Same-origin API proxy already used elsewhere; inspect and use same route.
- [ ] Read Spec and Task 1 schema/report. Apply relevant frontend and browser skill; existing visual system is binding.
- [ ] Generate API types with corepack pnpm generate:api-types from worktree; generator must not import source main accidentally through shared environment.
- [ ] Write form behavior tests RED: manual edit all values, submit payload, server breakdown, pending/error/retry, unverified metadata no public sums, invalid input, late response and result reset after editing.
- [ ] Implement responsive accessible form (labels/fieldset/aria-live/keyboard), sources, clear scope text and price/customs-cost distinction, metadata unavailable state; no invented examples or exact date from catalog year.
- [ ] Add nav and footer link «Таможенный калькулятор» to `/customs-calculator`.
- [ ] Run targeted Vitest GREEN, navigation tests, typecheck and production build. Inspect diff and commit only owned files. Full report with commands/results to .superpowers/sdd/customs-calculator/frontend-report.md.

## Task 3: Integration and final acceptance
**Ownership:** Controller coordinates read-only reviewers on Luna 6 max; fixes belong to original implementers. Controller owns docs/customs/IMPLEMENTATION_2026-10-04.md and ledger.
- [ ] Review each task against Spec and its diff file; resolve important findings with original agent, record result.
- [ ] Run combined frontend tests once, verify generated API types and correct noindex; focused backend tests on final code if changed.
- [ ] Launch only new loopback local ports after checking ownership, verify real GET/meta and real NBRB fetch; never stop foreign previews.
- [ ] Inspect browser desktop/mobile, validation/submission/unavailable gate; record screenshots/check evidence. Do not equate mocked UI calculation with public GTK acceptance.
- [ ] Final whole-feature read-only review including parked findings; single fix wave if needed.
- [ ] Save actual implemented/verified/unverified/deployed status; report branch, preview and precise remaining GTK gate if inaccessible.
