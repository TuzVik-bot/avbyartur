import type {
  ApiErrorShape,
  AuthSession,
  CatalogItem,
  Company,
  CompanySummary,
  ConversationMessage,
  ConversationSummary,
  ConversationThread,
  Listing,
  ListingDraftInput,
  ListingPhoto,
  ListingSearch,
  ListingSummary,
  ListResponse,
  Report,
  ReportCategory,
  UserNotificationList
} from "@/lib/types";
import type { components } from "@/lib/types.generated";

const API_PREFIX = "/api/v1";
let currentCsrfToken: string | undefined;
let otpCsrfToken: string | undefined;
let otpCsrfTokenExpiresAt = 0;
let guestContactRequestToken: string | undefined;
let guestContactRequestTokenExpiresAt = 0;
const GUEST_CONTACT_TOKEN_REFRESH_MS = 14 * 60 * 1000;

export function createIdempotencyKey() {
  return crypto.randomUUID();
}

function idempotencyHeaders(key?: string) {
  return { "Idempotency-Key": key || createIdempotencyKey() };
}

export class ApiClientError extends Error {
  status: number;
  code: string;
  fieldErrors: Record<string, string>;
  requestId?: string;

  constructor(status: number, error: Partial<ApiErrorShape>) {
    super(error.message || "Запрос не выполнен");
    this.name = "ApiClientError";
    this.status = status;
    this.code = error.code || "request_failed";
    this.fieldErrors = error.field_errors || {};
    this.requestId = error.request_id;
  }
}

export function setCsrfToken(token?: string) {
  currentCsrfToken = token;
  otpCsrfToken = undefined;
  otpCsrfTokenExpiresAt = 0;
}

export function resetCsrfToken() {
  currentCsrfToken = undefined;
  otpCsrfToken = undefined;
  otpCsrfTokenExpiresAt = 0;
}

export type AuthCapabilities = {
  sms_login: boolean;
  sms_registration: boolean;
  email_registration: boolean;
  email_verification: boolean;
  password_recovery: boolean;
};
export type NotificationPreferences = components["schemas"]["NotificationPreferencesOut"];
export type RegistrationConsentVersions = { terms: string; privacy: string };
export type ListingOptions = components["schemas"]["ListingOptionsOut"];
export type ListingValidationPolicy = components["schemas"]["ListingValidationPolicyOut"];

export type UserProfile = {
  id: string;
  display_name: string;
  contacts: {
    email: { masked: string | null; verified: boolean };
    phone: { masked: string | null; verified: boolean };
  };
};
export type ConsentHistoryItem = { document_type: string; version: string; accepted_at: string; source: string };
export type AccountDeletionResult = { status: "requested"; revoked_sessions: number; withdrawn_listings: number };

export function internalApiBase() {
  return `${(process.env.API_INTERNAL_URL || process.env.API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "")}${API_PREFIX}`;
}

function parseJson<T>(payload: unknown): T {
  return payload as T;
}

async function responseData<T>(response: Response): Promise<T> {
  const payload: unknown = response.status === 204 ? undefined : await response.json().catch(() => undefined);
  if (!response.ok) {
    throw new ApiClientError(response.status, (payload || {}) as Partial<ApiErrorShape>);
  }
  return parseJson<T>(payload);
}

async function ensureCsrfToken(path: string) {
  const preAuthOtp = ["auth/register", "auth/otp/request", "auth/register/otp/request", "auth/otp/verify"].includes(path.replace(/^\//, ""));
  if (preAuthOtp && otpCsrfToken && Date.now() < otpCsrfTokenExpiresAt) return otpCsrfToken;
  if (!preAuthOtp && currentCsrfToken) return currentCsrfToken;
  if (typeof window === "undefined") return undefined;

  const response = await fetch(`${API_PREFIX}/${preAuthOtp ? "auth/otp/csrf" : "me"}`, { credentials: "include", cache: "no-store" });
  if (!response.ok) return undefined;
  const session = (await response.json()) as Pick<AuthSession, "csrf_token">;
  if (preAuthOtp) {
    otpCsrfToken = session.csrf_token;
    // The pre-auth cookie lasts 15 minutes. Refresh a minute before it expires.
    otpCsrfTokenExpiresAt = Date.now() + 14 * 60 * 1000;
    return otpCsrfToken;
  }
  currentCsrfToken = session.csrf_token;
  return currentCsrfToken;
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method || "GET").toUpperCase();
  const headers = new Headers(init.headers);
  const isFormData = typeof FormData !== "undefined" && init.body instanceof FormData;
  if (init.body !== undefined && !isFormData && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const normalizedPath = path.replace(/^\//, "");
  const csrfExempt = new Set(["auth/login", "auth/recovery/request", "auth/recovery/confirm", "auth/email/verification/confirm"]).has(normalizedPath);
  if (!new Set(["GET", "HEAD", "OPTIONS"]).has(method) && !csrfExempt) {
    const token = await ensureCsrfToken(path);
    if (token) headers.set("X-CSRF-Token", token);
  }

  const base = typeof window === "undefined" ? internalApiBase() : API_PREFIX;
  const response = await fetch(`${base}/${path.replace(/^\//, "")}`, {
    ...init,
    method,
    headers,
    credentials: "include",
    cache: "no-store"
  });
  return responseData<T>(response);
}

type GuestContactCapabilities = components["schemas"]["ListingPublicCapabilitiesOut"];

async function loadGuestContactCapabilities(): Promise<GuestContactCapabilities> {
  const base = typeof window === "undefined" ? internalApiBase() : API_PREFIX;
  const response = await fetch(`${base}/listings/public-capabilities`, {
    credentials: "include",
    cache: "no-store"
  });
  const capabilities = await responseData<GuestContactCapabilities>(response);
  guestContactRequestToken = capabilities.guest_contact_reveal_enabled
    ? response.headers.get("X-Guest-Contact-Token") || undefined
    : undefined;
  guestContactRequestTokenExpiresAt = guestContactRequestToken
    ? Date.now() + GUEST_CONTACT_TOKEN_REFRESH_MS
    : 0;
  return capabilities;
}

async function revealListingPhone(id: string, asGuest: boolean): Promise<{ phone: string }> {
  if (asGuest && (!guestContactRequestToken || Date.now() >= guestContactRequestTokenExpiresAt)) {
    await loadGuestContactCapabilities();
  }

  const request = () => apiRequest<{ phone: string }>(
    `listings/${encodeURIComponent(id)}/phone-reveal`,
    {
      method: "POST",
      body: JSON.stringify({}),
      headers: asGuest && guestContactRequestToken
        ? { "X-Guest-Contact-Token": guestContactRequestToken }
        : undefined
    }
  );

  try {
    return await request();
  } catch (error) {
    if (!asGuest || !(error instanceof ApiClientError) || error.code !== "guest_contact_proof_required") {
      throw error;
    }
    guestContactRequestToken = undefined;
    guestContactRequestTokenExpiresAt = 0;
    await loadGuestContactCapabilities();
    return request();
  }
}

export function searchPath(search: ListingSearch = {}) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(search)) {
    if (Array.isArray(value)) {
      for (const entry of value) if (entry !== "") params.append(key, entry);
    } else if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const query = params.toString();
  return query ? `/api/v1/listings?${query}` : "/api/v1/listings";
}

export const api = {
  login: (email: string, password: string) => apiRequest<AuthSession>("auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  register: (data: { email: string; password: string; display_name: string; accept_terms: true; accept_privacy: true; terms_version: string; privacy_version: string }) => apiRequest<AuthSession>("auth/register", { method: "POST", body: JSON.stringify(data) }),
  authCapabilities: () => apiRequest<AuthCapabilities>("auth/capabilities"),
  requestLoginOtp: (phone: string) => apiRequest<components["schemas"]["OtpAcceptedResponse"]>("auth/otp/request", { method: "POST", body: JSON.stringify({ phone }), headers: idempotencyHeaders() }),
  requestRegistrationOtp: (data: { phone: string; display_name: string; accept_terms: true; accept_privacy: true; terms_version: string; privacy_version: string }) => apiRequest<components["schemas"]["OtpAcceptedResponse"]>("auth/register/otp/request", { method: "POST", body: JSON.stringify(data), headers: idempotencyHeaders() }),
  verifyPhoneOtp: (phone: string, code: string) => apiRequest<AuthSession>("auth/otp/verify", { method: "POST", body: JSON.stringify({ phone, code }) }),
  profile: () => apiRequest<{ profile: UserProfile }>("me/profile"),
  updateProfile: (display_name: string) => apiRequest<{ profile: UserProfile }>("me/profile", { method: "PATCH", body: JSON.stringify({ display_name }) }),
  consents: () => apiRequest<{ items: ConsentHistoryItem[] }>("me/consents"),
  requestEmailVerification: (email: string) => apiRequest<{ accepted: true }>("auth/email/verification/request", { method: "POST", body: JSON.stringify({ email }) }),
  confirmEmailVerification: (token: string) => apiRequest<{ verified: true }>("auth/email/verification/confirm", { method: "POST", body: JSON.stringify({ token }) }),
  requestPasswordRecovery: (email: string) => apiRequest<{ accepted: true }>("auth/recovery/request", { method: "POST", body: JSON.stringify({ email }) }),
  confirmPasswordRecovery: (token: string, new_password: string) => apiRequest<{ ok: true }>("auth/recovery/confirm", { method: "POST", body: JSON.stringify({ token, new_password }) }),
  requestAccountDeletion: () => apiRequest<AccountDeletionResult>("me/deletion-requests", { method: "POST", body: JSON.stringify({ confirmation: "DELETE" }) }),
  notificationPreferences: () => apiRequest<{ preferences: NotificationPreferences }>("me/notification-preferences"),
  updateNotificationPreferences: (data: Pick<components["schemas"]["NotificationPreferencesInput"], "web_enabled" | "email_enabled" | "expected_revision">) => apiRequest<{ preferences: NotificationPreferences }>("me/notification-preferences", { method: "PUT", body: JSON.stringify(data) }),
  requestPhoneChange: (phone: string) => apiRequest<components["schemas"]["PhoneChangeAcceptedResponse"]>("me/profile/phone-change/request", { method: "POST", body: JSON.stringify({ phone }), headers: idempotencyHeaders() }),
  confirmPhoneChange: (challenge_id: string, old_code: string, new_code: string) => apiRequest<components["schemas"]["PhoneChangeConfirmedResponse"]>("me/profile/phone-change/confirm", { method: "POST", body: JSON.stringify({ challenge_id, old_code, new_code }) }),
  logout: () => apiRequest<{ ok: true }>("auth/logout", { method: "POST", body: JSON.stringify({}) }),
  me: () => apiRequest<AuthSession>("me"),
  notifications: (options: { unreadOnly?: boolean; limit?: number } = {}) => {
    const params = new URLSearchParams();
    if (options.unreadOnly) params.set("unread_only", "true");
    if (options.limit !== undefined) params.set("limit", String(options.limit));
    const query = params.toString();
    return apiRequest<UserNotificationList>(`me/notifications${query ? `?${query}` : ""}`);
  },
  conversations: () => apiRequest<{ items: ConversationSummary[] }>("conversations"),
  createConversation: (listingId: string, message: string, idempotencyKey?: string) => apiRequest<{ conversation: ConversationSummary }>("conversations", { method: "POST", body: JSON.stringify({ listing_id: listingId, message }), headers: idempotencyHeaders(idempotencyKey) }),
  conversation: (id: string, options: { beforeSequence?: number; limit?: number } = {}) => {
    const params = new URLSearchParams();
    if (options.limit !== undefined) params.set("limit", String(options.limit));
    if (options.beforeSequence !== undefined) params.set("before_sequence", String(options.beforeSequence));
    const query = params.toString();
    return apiRequest<ConversationThread>(`conversations/${encodeURIComponent(id)}${query ? `?${query}` : ""}`);
  },
  sendConversationMessage: (id: string, message: string, idempotencyKey?: string) => apiRequest<{ message: ConversationMessage }>(`conversations/${encodeURIComponent(id)}/messages`, { method: "POST", body: JSON.stringify({ message }), headers: idempotencyHeaders(idempotencyKey) }),
  markConversationRead: (id: string, idempotencyKey?: string) => apiRequest<{ ok: true }>(`conversations/${encodeURIComponent(id)}/read`, { method: "POST", body: JSON.stringify({}), headers: idempotencyHeaders(idempotencyKey) }),
  blockConversation: (id: string, idempotencyKey?: string) => apiRequest<{ ok: true }>(`conversations/${encodeURIComponent(id)}/block`, { method: "POST", body: JSON.stringify({}), headers: idempotencyHeaders(idempotencyKey) }),
  markNotificationRead: (id: string) => apiRequest<{ ok: true }>(`me/notifications/${encodeURIComponent(id)}/read`, { method: "POST", body: JSON.stringify({}) }),
  listings: (search: ListingSearch = {}) => apiRequest<ListResponse<ListingSummary> & { fx?: { rate_date: string; usd_rate: string; scale: number } }>(searchPath(search).replace("/api/v1/", "")),
  listing: (id: string) => apiRequest<{ listing: Listing }>(`listings/${encodeURIComponent(id)}`),
  catalog: (kind: "makes" | "models" | "generations" | "body-types" | "body-variants" | "modifications", params: Record<string, string> = {}) => {
    const query = new URLSearchParams(params).toString();
    return apiRequest<{ items: CatalogItem[] }>(`catalog/${kind}${query ? `?${query}` : ""}`);
  },
  listingOptions: () => apiRequest<ListingOptions>("listing-options"),
  listingValidationPolicy: () => apiRequest<ListingValidationPolicy>("listing-validation-policy"),
  createBillingOrder: (data: components["schemas"]["BillingOrderCreate"], idempotencyKey?: string) => apiRequest<components["schemas"]["BillingCheckoutOut"]>("billing/orders", { method: "POST", body: JSON.stringify(data), headers: idempotencyHeaders(idempotencyKey) }),
  regions: () => apiRequest<{ items: CatalogItem[] }>("locations/regions"),
  cities: (regionId: string) => apiRequest<{ items: CatalogItem[] }>(`locations/cities?region_id=${encodeURIComponent(regionId)}`),
  myListings: () => apiRequest<ListResponse<Listing>>("me/listings"),
  favorites: () => apiRequest<{ items: ListingSummary[] }>("me/favorites"),
  addFavorite: (id: string) => apiRequest<{ ok: true }>(`me/favorites/${encodeURIComponent(id)}`, { method: "PUT" }),
  removeFavorite: (id: string) => apiRequest<{ ok: true }>(`me/favorites/${encodeURIComponent(id)}`, { method: "DELETE" }),
  guestContactEnabled: () => loadGuestContactCapabilities(),
  revealPhone: (id: string, asGuest = false) => revealListingPhone(id, asGuest),
  createReport: (id: string, data: { category: ReportCategory; comment: string }) => apiRequest<{ id: string; status: string }>(`listings/${encodeURIComponent(id)}/reports`, { method: "POST", body: JSON.stringify(data) }),
  createDraft: (data: Partial<ListingDraftInput>) => apiRequest<{ listing: Listing }>("listings/drafts", { method: "POST", body: JSON.stringify(data), headers: { "Idempotency-Key": crypto.randomUUID() } }),
  updateDraft: (id: string, revision: number, data: Partial<ListingDraftInput>) => apiRequest<{ listing: Listing }>(`listings/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify({ ...data, expected_revision: revision }) }),
  submitListing: (id: string, revision: number) => apiRequest<{ listing: Listing }>(`listings/${encodeURIComponent(id)}/submit`, { method: "POST", body: JSON.stringify({ expected_revision: revision }), headers: { "Idempotency-Key": crypto.randomUUID() } }),
  listingAction: (id: string, action: "pause" | "resume" | "sold", revision: number) => apiRequest<{ listing: Listing }>(`listings/${encodeURIComponent(id)}/${action}`, { method: "POST", body: JSON.stringify({ expected_revision: revision }) }),
  uploadPhoto: (id: string, file: File) => {
    const formData = new FormData();
    formData.set("file", file);
    return apiRequest<{ id: string; status: string; url?: string }>(`listings/${encodeURIComponent(id)}/photos`, { method: "POST", body: formData, headers: { "Idempotency-Key": crypto.randomUUID() } });
  },
  photos: (id: string) => apiRequest<{ items: ListingPhoto[] }>(`listings/${encodeURIComponent(id)}/photos`),
  deletePhoto: (id: string, photoId: string) => apiRequest<{ ok: true }>(`listings/${encodeURIComponent(id)}/photos/${encodeURIComponent(photoId)}`, { method: "DELETE" }),
  reorderPhotos: (id: string, photoIds: string[]) => apiRequest<{ ok: true }>(`listings/${encodeURIComponent(id)}/photos/reorder`, { method: "POST", body: JSON.stringify({ photo_ids: photoIds }) }),
  setCover: (id: string, photoId: string) => apiRequest<{ ok: true }>(`listings/${encodeURIComponent(id)}/photos/${encodeURIComponent(photoId)}/cover`, { method: "POST", body: JSON.stringify({}) }),
  company: () => apiRequest<{ company: Company | null }>("me/company"),
  createCompany: (data: components["schemas"]["CompanyInput"]) => apiRequest<{ company: Company }>("companies", { method: "POST", body: JSON.stringify(data), headers: { "Idempotency-Key": crypto.randomUUID() } }),
  updateCompany: (id: string, revision: number, data: components["schemas"]["CompanyInput"]) => apiRequest<{ company: Company }>(`companies/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify({ ...data, expected_revision: revision }) }),
  dealers: () => apiRequest<ListResponse<CompanySummary>>("dealers"),
  dealer: (slug: string) => apiRequest<{ company: CompanySummary; listings: ListResponse<ListingSummary> }>(`dealers/${encodeURIComponent(slug)}`),
  moderationListings: () => apiRequest<{ items: Listing[] }>("moderation/listings"),
  moderateListing: (id: string, action: "approve" | "reject" | "block", revision: number, reason?: string) => apiRequest<{ listing: Listing }>(`moderation/listings/${encodeURIComponent(id)}/${action}`, { method: "POST", body: JSON.stringify({ expected_revision: revision, ...(reason ? { reason } : {}) }) }),
  moderationCompanies: () => apiRequest<{ items: Company[] }>("moderation/companies"),
  moderateCompany: (id: string, action: "approve" | "reject" | "block", revision: number, reason?: string) => apiRequest<{ company: Company }>(`moderation/companies/${encodeURIComponent(id)}/${action}`, { method: "POST", body: JSON.stringify({ expected_revision: revision, ...(reason ? { reason } : {}) }) }),
  moderationReports: () => apiRequest<{ items: Report[] }>("moderation/reports"),
  resolveReport: (id: string, resolution: string) => apiRequest<{ report: Report }>(`moderation/reports/${encodeURIComponent(id)}/resolve`, { method: "POST", body: JSON.stringify({ resolution }) })
};
