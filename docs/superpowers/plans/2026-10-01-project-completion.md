# Авторынок: план полного завершения

> **For agentic workers:** Use superpowers:subagent-driven-development. Track progress in `.superpowers/sdd/2026-10-01-project-completion/progress.md` and preserve other workers' edits.

**Goal:** завершить обязательный функционал исходного ТЗ §§1–18 и все gates пилота, с доказательствами приёмки и явными внешними зависимостями.

**Architecture:** существующие FastAPI/Next.js/PostgreSQL/worker/private media. Новые backend подсистемы выделяются в собственные router/schema/service modules; общий main/OpenAPI интегрирует координатор.

**Tech Stack:** Python 3.12, SQLAlchemy/Alembic, PostgreSQL 17.11, React/Next.js, TypeScript, pnpm/uv, pytest/Vitest/Playwright.

**Spec:** `docs/superpowers/specs/2026-10-01-project-completion-design.md`.

## Global Constraints

- Нет Git; не выполнять commit/worktree commands. Сохранять исходную папку и ownership файлов.
- Не печатать credentials и значения `.env`; test configs mode 600.
- Backend интеграционные тесты только dedicated *_test с TEST_DATABASE_DISPOSABLE_CONFIRMATION, совпадающим с именем; не preview и не runtime DB.
- VPS Basic Auth/noindex, именованные тома и реальные данные сохраняются. Нет deploy/remote mutations до отдельного запроса.
- Каждый новый поведенческий сценарий: воспроизвести failing test, реализовать, проверить. Не считать skipped integration доказательством.
- Координатор владеет `backend/app/main.py`, generated types, общими acceptance/ops документами и admin API. Исполнители не редактируют эти файлы параллельно.

## Пакеты исполнения

### Task 1: исходный срез, ownership, isolated testing

**Files:** этот plan/spec; `.superpowers/sdd/2026-10-01-project-completion/progress.md`; protected test runtime config в `/private/tmp`.

- [x] Сверить current VPS read-only, аккаунты, свежий backup, код и базовый live smoke.
- [x] Запросить внешние данные и запустить три Luna max inventory lanes.
- [ ] Создать независимые disposable test DB для core/identity/dealer; сохранить команды запуска без секретов в ledger.
- [ ] Сохранить обязательную матрицу исходного ТЗ и уточнённые subtask contracts по результатам inventory.

### Task 2: identity/delivery

**Owner:** identity_delivery. **Files:** `backend/app/api/auth.py`, `backend/app/config.py`, `backend/app/sms_auth.py`, `backend/app/worker.py`, `backend/app/notification_service.py`, новые provider/account modules и собственные tests.

**Interfaces:** existing get_sms_provider/SmsCodeProvider; notification outbox; existing session/CSRF/user serializers. New account endpoints/contracts согласовать с frontend до реализации.

- [ ] Тесты unconfigured/configured transport, timeout/retry/idempotency/redaction.
- [ ] Реальный provider adapter выбранного поставщика и SMTP email delivery; не отправлять внешние сообщения во время тестов.
- [ ] Profile/recovery/account deletion flow, consent history и session protection.
- [ ] Targeted identity/notification tests на identity test DB; отчёт с red/green evidence.

### Task 3: dealer/team/feed/analytics

**Owner:** dealer_commerce. **Files:** new dealer API/schema/service modules, `backend/app/models.py`, Alembic revisions, own tests. Не редактировать auth/config/worker/main/общие schemas без согласования.

- [ ] Зафиксировать scopes company/team/feed endpoints и семантику external IDs/dry-run/error history.
- [ ] Тесты cross-company denial, role capabilities, malformed/oversize XML/CSV, duplicate/replayed sync и premoderation.
- [ ] Реализовать команды, feeds и seller analytics без обхода existing listing services.
- [ ] Миграции проверяются на clean DB и upgrade с 0011; tests на dealer test DB.

### Task 4: commerce

**Owner:** dealer_commerce после Task 3; frontend owner реализует UI. **Files:** new billing/promotion API/schema/service/model/migration/tests.

- [ ] Зафиксировать order snapshot, provider reference, callback verification и activation overlap contract.
- [ ] Тесты amount/currency mismatch, invalid auth/signature, out-of-order/repeated callback и concurrent duplicate activation.
- [ ] Реализовать price snapshot/tariffs/history/promotion durations. Enabled pricing приходит от владельца, не выдумывается.
- [ ] Checkout/callback adapter выбранного реального provider; production capability disabled до внешних условий.
- [ ] Полный sandbox order → callback → activation → search rendering flow.

### Task 5: administrative management

**Owner:** coordinator. **Files:** `backend/app/api/admin.py`, `backend/app/admin_schemas.py`, `backend/tests/test_admin_management.py`, `backend/app/main.py`; frontend owner `/admin` UI.

**Interfaces:** `/api/v1/admin/users` paginated read; PATCH `/api/v1/admin/users/{user_id}` reason/expected current role+status; `/api/v1/admin/audit`; `/api/v1/admin/operations` bounded summary. Role/status edits require CSRF/admin and revoke existing target sessions.

- [ ] Написать failing tests forbidden user/moderator access, CSRF, pagination, session revocation, reason/audit, last-admin protection и concurrent stale changes.
- [ ] Реализовать safe serializers и actor/target locking; интегрировать typed OpenAPI.
- [ ] Доработать versioned справочники/лимиты/templates/SEO и усиленную admin verification по отдельному subtask contract.
- [ ] Targeted tests core DB, review и frontend acceptance.

### Task 6: complete listing/search/anti-fraud contracts

**Owner:** coordinator после Task 5; frontend owner реализует поля/фильтры. **Files:** listings services/routes/schemas/risk modules, model/migrations через dealer owner, dedicated tests.

- [ ] Сверить поля ТЗ: цвет/таможня/торг/обмен/кредит/лизинг/комплектация/время звонков; related listings и statistics.
- [ ] Реализовать отсутствующие поля, filters/snapshot serialization с revision validation.
- [ ] Закрыть pHash и change-risk signals; сохранить advisory/manual moderation semantics.
- [ ] Проверить catalog controls по источникам; не выдумывать generation bounds.

### Task 7: frontend completion

**Owner:** frontend_completion. **Files:** web/ кроме generated types; current design tokens remain.

- [ ] Admin users/audit UI и profile/deletion/recovery.
- [ ] Dealer team/feed/history/analytics и billing/tariff/order/promotion pages после фиксации backend contracts.
- [ ] Complete listing/search fields и related listings.
- [ ] Runtime provider/launch readiness показывается честно; legal/operator configuration и consent UI по реальным данным.
- [ ] Vitest interaction/error-state checks, typecheck/build, responsive/keyboard/200% browser verification.

### Task 8: monitoring/operational readiness

**Owner:** coordinator, затем освобождённый agent. **Files:** new runtime health/monitor helpers, scripts tests и deployment docs.

- [ ] Queue/notification/provider/feed/backup metrics and actionable alerts; secrets/redaction tests.
- [ ] Encrypted offsite preflight/transfer, retention и deterministic restore verification.
- [ ] Проверить отдельный full release-image restore и measured RPO/RTO после target доступа.

### Task 9: whole-system integration and acceptance

**Owner:** coordinator/reviewer lanes после реализации. **Files:** generated types, API contract, acceptance runner/tests, актуальные docs.

- [ ] Сгенерировать OpenAPI types; полные backend/web/ops checks на собственных одноразовых данных.
- [ ] Stateful частник → фото → moderation → buyer/favorites/contact → lifecycle.
- [ ] Stateful компания → approval → team/feed → publication → blocking; chat/email и sandbox commerce.
- [ ] 10000 listings/20 VU/20 RPS load exact candidate image, p95<=500 ms; restore/photo checksum; phone HEIC и mobile UX.
- [ ] Независимые spec/code/security review lanes, исправить findings; матрица §§1–18 с каждым evidence scope.

### Task 10: concrete release and external completion

**Owner:** coordinator. **Files:** candidate release manifest, runbook/rollback, actual acceptance report.

- [ ] Подготовить candidate и rollback с точными image/source identities, deployment preflight и backups.
- [ ] Подключить предоставленные реальные providers/offsite/legal configuration и закрыть внешние gates.
- [ ] Получить отдельное явное указание deploy перед VPS migrations/switch; сохранить barriers/data/volumes.
- [ ] Fresh deployed stateful/live acceptance на разрешённых реальных данных; публичность только с отдельным разрешением.
- [ ] Final completion audit всех требований; goal complete только если нет обязательных открытых условий.
