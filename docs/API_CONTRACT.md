# API Contract v1

All application routes use `/api/v1`. JSON errors use `{ "code": string, "message": string, "field_errors": Record<string,string>, "request_id": string }`. Money amounts are decimal strings. The browser uses same-origin requests with credentials and sends `X-CSRF-Token` for state-changing requests.

Unknown API paths and unsupported methods use the same error envelope and return the correlated `X-Request-ID` header.

## Shared shapes

`User = { id, email, display_name, role: "user"|"moderator"|"admin", company_id: string|null }`

`CatalogItem = { id, slug, name, aliases?: string[], make_id?: string, model_id?: string, year_from?: number|null, year_to?: number|null }`

`CatalogModification = CatalogItem & { source?: { name: "Drom", id: string|null, url: string|null }, specs?: { engine_code: string|null, frame_code: string|null, engine_l: number|null, power_hp: number|null, fuel: string|null, transmission: string|null, drive: string|null, production_period_raw: string|null, summary_raw: string|null } }`

`Seller = { type: "private"|"company", id, name, slug?: string }`

`Company = { id, name, slug, status, revision: number, address }` with `unp`, `phone`, and `moderation_reason` on private or moderation responses.

`Report = { id, listing_id, category, comment, status, revision: number, resolution?, created_at? }`.

`ListingSummary = { id, slug, title, make: CatalogItem, model: CatalogItem, generation?: CatalogItem|null, year, mileage_km, fuel, transmission, drive, body_type?: string|null, body_variant_id?: string|null, body_variant?: CatalogItem|null, price: { amount: string, currency: "BYN"|"USD", display_amount?: string, display_currency?: "BYN"|"USD", display_byn?: string|null, rate_date?: string|null }, region: CatalogItem, city: CatalogItem|null, manual_city: string|null, cover_url?: string|null, seller: Seller, created_at, damaged: boolean, parts_only: boolean }`. In incomplete drafts, `price`, `region`, and other unfilled fields may be `null`.

`Listing = ListingSummary & { status, revision: number, description, engine_volume_l?: string|null, power_hp?: number|null, condition, vin?: string|null, photo_urls: string[], contact_phone?: string }`. Public/search summaries omit `contact_phone`; seller-owned listing responses may include it so the seller can restore the number while editing. Other viewers use the explicit contact reveal action. Seller-owned listing responses also include `photos: { id, url?, status, position, is_cover }[]` so reordering and cover selection survive reloads.

Full listing detail and seller single-listing responses may also include `modification: { id, slug, name, source?, specs? } | null`. Drom-selected modifications include the source/specs envelope above. Search summaries omit the modification object. Listings with no selected modification return `modification: null` in full detail.

List responses use `{ items: T[], pagination?: { page, page_size, total, pages } }`.

## Authentication

- `POST /auth/login` `{ email, password }` -> `{ user: User, csrf_token: string }`, sets a same-origin secure session cookie.
- `POST /auth/logout` -> `{ ok: true }`, requires CSRF token.
- `GET /me` -> `{ user: User, csrf_token: string }`.

## Catalog and locations

- `GET /catalog/makes?q=` -> `{ items: CatalogItem[] }`.
- `GET /catalog/models?make_id=&q=` -> `{ items: CatalogItem[] }`.
- `GET /catalog/generations?model_id=` -> `{ items: CatalogItem[] }`.
- `GET /catalog/body-types` -> `{ items: CatalogItem[] }`.
- `GET /catalog/body-variants?generation_id=` -> `{ items: CatalogItem[] }`.
- `GET /catalog/modifications?generation_id=` -> `{ items: CatalogModification[] }`. Drom-backed items include `source` and `specs`; other sources retain the existing catalog item shape.
- `GET /catalog/makes?q=` includes exact Drom make rows added by an authorized batch, including Chevrolet and Honda when absent from the current catalog.
- `GET /locations/regions` -> `{ items: CatalogItem[] }`.
- `GET /locations/cities?region_id=` -> `{ items: CatalogItem[] }`.

## Search and listing detail

- `GET /listings` accepts `q`, catalog IDs including `make_id`, `model_id`, `generation_id`, `body_variant_id`, and `modification_id`, `price_min`, `price_max`, `currency` (`BYN|USD`), `year_min`, `year_max`, `mileage_min`, `mileage_max`, `fuel`, `transmission`, `drive`, `body_type`, `damaged`, `parts_only`, `condition`, `region_id`, `city_id`, `seller_type`, `page`, `page_size`, and `sort` (`newest|price_asc|price_desc|year_desc|mileage_asc`). `modification_id` and `body_variant_id` are UUIDs and filter by exact catalog records; each combines conjunctively with `generation_id` and other filters. Malformed UUIDs return the standard `422 validation_error`. Search returns safe `ListingSummary` values without modification source metadata. Returns `ListResponse<ListingSummary>` plus optional `fx: { rate_date, usd_rate, scale }`. With a fresh official USD rate (fetched within 72 hours, dated no later than today), `fx` is present and each priced item has `display_byn` and `rate_date`. If `currency` is supplied, its search results also have `display_amount` (decimal string rounded to two places) and `display_currency`; the original `amount` and `currency` stay unchanged. Without a fresh rate, these display fields and `fx` are omitted (while base `display_byn` and `rate_date` remain `null`).
- `price_min`, `price_max`, `price_asc`, and `price_desc` require `currency`; otherwise the API returns `422 currency_required`. These operations compare prices converted to the selected currency and require a fresh rate; without one the API returns `422 exchange_rate_unavailable`. Other filters and sorts still work without a fresh rate, including when `currency` is supplied.
- `GET /listings/{id}` -> `{ listing: Listing }`; public viewers and moderators who do not own the listing omit `contact_phone`, while the authenticated owner receives it on their own detail and seller-workspace responses. The detail price defaults to BYN: when a fresh rate is available, `display_amount`/`display_currency` show the BYN amount while original `amount`/`currency` remain unchanged; `display_byn` and `rate_date` are also populated. Without a fresh rate, the display pair is omitted and the UI falls back to the original price.
- `GET /listings/public-capabilities` -> `{ guest_contact_reveal_enabled: boolean }`, `Cache-Control: no-store`. Guest contact is disabled by default. When enabled, the response provides a signed proof in `X-Guest-Contact-Token` and the `avtorinok_guest_contact_proof` HttpOnly, SameSite=Strict cookie (15 minutes); the browser also receives the `avtorinok_guest_contact_device` HttpOnly, SameSite=Strict cookie (24 hours). Both use `Secure` according to session-cookie configuration and `Path=/`. A still-valid proof is reused on capability refresh so parallel pages remain usable. With the feature disabled, these cookies are deleted and no guest-contact cookies persist.
- `POST /listings/{id}/phone-reveal` -> `{ phone: string }`, only for an active public listing. Signed-in viewers require CSRF and are limited to 30 reveals per account per hour; actor status and session validity are rechecked before contact is recorded. When guest contact is enabled, anonymous viewers require the matching proof cookie and `X-Guest-Contact-Token`; limits are 30 per IP, 30 per device, and 300 per listing per hour. Raw IP addresses are not retained in rate-limit rows or contact events. Forwarded client IP is not trusted until the VPS proxy chain is verified.
- `POST /listings/{id}/reports` `{ category, comment }` -> `{ id, status, revision }`.

## Seller workspace

- `POST /listings/drafts` requires `Idempotency-Key`, creates an incomplete autosaved draft and accepts any subset of `{ seller_type: "private"|"company", make_id, model_id, generation_id?, body_type_id?, body_variant_id?, modification_id?, year, mileage_km, fuel, transmission, drive, condition, damaged, parts_only, price: { amount: string, currency: "BYN"|"USD" }, region_id, city_id, manual_city?, description, engine_volume_l?, power_hp?, vin?, contact_phone? }`. `manual_city` is a nullable string of at most 160 characters; the API trims it, collapses whitespace, and treats blank input as `null`. `city_id` and a nonblank `manual_city` cannot both be set (`422 invalid_location`); send `null` for the old field when switching modes. Submission requires `region_id` and either a catalog `city_id` or `manual_city`. Responses return `city: null` for manual locations and preserve `manual_city` in `Listing`. Company ownership is derived from the session. Returns `{ listing: Listing }`.
- `PATCH /listings/{id}` accepts changed fields from the draft shape plus `expected_revision`; returns `{ listing: Listing }`.
- `POST /listings/{id}/submit` requires `Idempotency-Key`, accepts `{ expected_revision }` -> `{ listing: Listing }`.
- `POST /listings/{id}/pause|resume|sold` `{ expected_revision }` -> `{ listing: Listing }`.
- `GET /me/listings` -> `ListResponse<Listing>`.
- `GET /me/favorites` -> `{ items: ListingSummary[] }`.
- `PUT /me/favorites/{listing_id}` and `DELETE /me/favorites/{listing_id}` -> `{ ok: true }` (idempotent).
- `POST /listings/{id}/photos` multipart field `file` -> `{ id, status: "queued"|"processing"|"ready"|"failed" }`.
- `GET /listings/{id}/photos` -> `{ items: { id, status, position, is_cover, error? }[] }` for the owner in any state, or moderator/admin while the listing is `pending_review`; other callers receive 404. This exposes processing metadata only: each photo URL remains independently protected by the private-photo access rules. The UI polls while queued or processing.
- `DELETE /listings/{id}/photos/{photo_id}` `{ expected_revision }`, `POST /listings/{id}/photos/reorder` `{ expected_revision, photo_ids: string[] }`, and `POST /listings/{id}/photos/{photo_id}/cover` `{ expected_revision }` update only the owner’s draft and reject stale revisions with `409`.

## Saved searches

- `GET /me/saved-searches` requires an authenticated session and returns `{ items: SavedSearch[] }` for the current user only.
- `POST /me/saved-searches` requires both CSRF and an `Idempotency-Key`. The body is `{ name, url, filters, notifications_enabled?, notification_channel?: "email"|"web"|null, notification_frequency?: "instant"|"daily"|"weekly" }`; `url` is a relative `/cars` search URL and `filters` contains the structured listing filter values. The response is `{ saved_search: SavedSearch }`.
- `PATCH /me/saved-searches/{id}` requires CSRF and accepts any changed saved-search fields plus optional `expected_revision`; it returns `{ saved_search: SavedSearch }`.
- `POST /me/saved-searches/{id}/pause|resume` requires CSRF and accepts optional `{ expected_revision }`; each returns `{ saved_search: SavedSearch }`. `DELETE /me/saved-searches/{id}` requires CSRF and returns `{ ok: true }`.
- `SavedSearch` is `{ id, name, url, filters, status: "active"|"paused", revision, notifications_enabled, notification_channel, notification_frequency, notification: { enabled, channel, frequency }, created_at, updated_at }`. When a listing becomes `active`, the same transaction queues a durable `saved-search.match` worker job if an eligible subscriber exists; the worker later creates outbox records and queues delivery jobs. The local `web` channel is delivered to the in-app notifications API; `email` rows are retained as `unsupported` until a real provider is configured, and no email, SMS, or Telegram message is claimed.
- Saved searches are limited per account and mutation requests are rate-limited. A saved-search owned by another account is returned as `404`.

## In-app notifications

- `GET /me/notifications?unread_only=false&limit=50` requires an authenticated session and returns `{ items: UserNotification[], unread_count }`. Items are scoped to the current user and contain `{ id, saved_search_id, listing_id, title, body, url, read_at, created_at }`.
- `POST /me/notifications/{id}/read` requires CSRF and returns `{ ok: true }`; an unknown notification, including one owned by another account, returns `404`.

## Companies and moderation

- `GET /me/company` -> `{ company: Company|null }`.
- `POST /companies` uses `{ name, unp, address, phone }` -> `{ company: Company }`; creation does not imply verification. `PATCH /companies/{id}` uses the same fields plus `{ expected_revision }` and increments the company revision.
- `GET /dealers` -> `ListResponse<CompanySummary>`; `GET /dealers/{slug}` -> `{ company: Company, listings: ListResponse<ListingSummary> }` for approved companies only.
- `GET /moderation/listings?status=pending_review|active` -> `{ items: Listing[], pagination }`, moderator/admin only; defaults to `pending_review`.
- `POST /moderation/listings/{id}/approve` `{ expected_revision }` -> `{ listing: Listing }`; only the current submitted `pending_review` revision can be approved.
- `POST /moderation/listings/{id}/reject` `{ expected_revision, reason }` -> `{ listing: Listing }`; only the current submitted `pending_review` revision can be rejected.
- `POST /moderation/listings/{id}/block` `{ expected_revision, reason }` -> `{ listing: Listing }`; a pending review or active listing can be blocked at its current revision. A reason is required; the change records both a listing status event and an audit event.
- `GET /moderation/companies|reports` -> `{ items: ...[] }`, moderator/admin only.
- `POST /moderation/companies/{id}/approve` `{ expected_revision }` -> `{ company: Company }`, admin only.
- `POST /moderation/companies/{id}/reject|block` `{ expected_revision, reason }` -> `{ company: Company }`, moderator/admin only; a reason is required. Company decisions increment the revision and stale requests return `409`.
- `POST /moderation/reports/{id}/resolve` `{ expected_revision, resolution }` -> `{ report: Report }`; resolution increments the report revision and stale requests return `409`.

## Health

- `GET /health/live` -> `200 { status: "ok" }` when the API process responds.
- `GET /health/ready` -> `200 { status: "ok" }` only when PostgreSQL is ready; otherwise `503`.

This contract is the integration target. If an implementation must differ, update this file and both consumers in the same change.

## Company API feed credentials in the closed pilot

`POST /api/v1/dealer/feeds/{feed_id}/api-imports` accepts a company-scoped
`Authorization: Bearer` token, or `X-Dealer-Feed-Token`. The second transport
keeps `Authorization: Basic` available to the outer closed-pilot gateway.
The web proxy forwards `X-Dealer-Feed-Token` and Bearer authorization only to that import route and
never forwards the gateway's Basic credential to the application API.

Do not put feed keys in query strings or import rows. Supplying a feed header
alongside a non-Basic Authorization scheme is rejected as ambiguous. Both
transports require the same active feed, token digest, approved company and
fresh scope validation; neither enables publication automatically. All named
volume, Basic Auth and noindex barriers stay in place.
