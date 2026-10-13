import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClientError, api, apiRequest, resetCsrfToken, setCsrfToken } from "@/lib/api";

afterEach(() => {
  resetCsrfToken();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("same-origin API client", () => {
  it("bootstraps and sends the guest contact request proof", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ guest_contact_reveal_enabled: true }), { status: 200, headers: { "Content-Type": "application/json", "X-Guest-Contact-Token": "guest-proof" } }))
      .mockResolvedValueOnce(new Response("{}", { status: 401, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ phone: "+375291234567" }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    expect(await api.guestContactEnabled()).toEqual({ guest_contact_reveal_enabled: true });
    await api.revealPhone("listing-1", true);

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/v1/listings/public-capabilities",
      "/api/v1/me",
      "/api/v1/listings/listing-1/phone-reveal"
    ]);
    const revealInit = (fetchMock.mock.calls[2] as [string, RequestInit])[1];
    expect(new Headers(revealInit.headers).get("X-Guest-Contact-Token")).toBe("guest-proof");
  });

  it("sends credentials and the in-memory CSRF token for writes", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "draft-1" }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    setCsrfToken("session-csrf");

    await apiRequest<{ id: string }>("listings/drafts", { method: "POST", body: JSON.stringify({ seller_type: "private" }) });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/listings/drafts");
    expect(init.credentials).toBe("include");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("session-csrf");
    expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
  });

  it("fetches the pre-auth OTP CSRF token before requesting a one-time code", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ csrf_token: "otp-csrf" }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ accepted: true }), { status: 202, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await api.requestLoginOtp("+375291234567");

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(["/api/v1/auth/otp/csrf", "/api/v1/auth/otp/request"]);
    const init = (fetchMock.mock.calls[1] as [string, RequestInit])[1];
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("otp-csrf");
    expect(new Headers(init.headers).get("Idempotency-Key")).toBeTruthy();
    expect(JSON.parse(init.body as string)).toEqual({ phone: "+375291234567" });
  });

  it("refreshes the short-lived pre-auth OTP CSRF token before it expires", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ csrf_token: "otp-csrf-1" }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ accepted: true }), { status: 202, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ csrf_token: "otp-csrf-2" }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ accepted: true }), { status: 202, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await api.requestLoginOtp("+375291234567");
    vi.advanceTimersByTime(14 * 60 * 1000 + 1);
    await api.requestLoginOtp("+375291234567");

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/v1/auth/otp/csrf", "/api/v1/auth/otp/request", "/api/v1/auth/otp/csrf", "/api/v1/auth/otp/request"
    ]);
    expect(new Headers((fetchMock.mock.calls[1] as [string, RequestInit])[1].headers).get("X-CSRF-Token")).toBe("otp-csrf-1");
    expect(new Headers((fetchMock.mock.calls[3] as [string, RequestInit])[1].headers).get("X-CSRF-Token")).toBe("otp-csrf-2");
  });

  it("keeps generic password recovery independent of an authenticated session", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ accepted: true }), { status: 202, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await api.requestPasswordRecovery("person@example.test");

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/auth/recovery/request");
    expect(new Headers(init.headers).has("X-CSRF-Token")).toBe(false);
  });

  it("uses the profile, consent, verification, and deletion contracts with session CSRF", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ profile: { id: "profile-1", display_name: "Пилот", contacts: { email: { masked: "p***@example.test", verified: false }, phone: { masked: null, verified: false } } } }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ profile: { id: "profile-1", display_name: "Новое имя", contacts: { email: { masked: "p***@example.test", verified: false }, phone: { masked: null, verified: false } } } }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [] }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ accepted: true }), { status: 202, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ verified: true }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "requested", revoked_sessions: 2, withdrawn_listings: 1 }), { status: 202, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    setCsrfToken("account-csrf");

    await api.profile();
    await api.updateProfile("Новое имя");
    await api.consents();
    await api.requestEmailVerification("pilot@example.test");
    await api.confirmEmailVerification("email-token");
    await api.requestAccountDeletion();

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/v1/me/profile", "/api/v1/me/profile", "/api/v1/me/consents",
      "/api/v1/auth/email/verification/request", "/api/v1/auth/email/verification/confirm", "/api/v1/me/deletion-requests"
    ]);
    expect(JSON.parse((fetchMock.mock.calls[1] as [string, RequestInit])[1].body as string)).toEqual({ display_name: "Новое имя" });
    expect(JSON.parse((fetchMock.mock.calls[3] as [string, RequestInit])[1].body as string)).toEqual({ email: "pilot@example.test" });
    expect(JSON.parse((fetchMock.mock.calls[4] as [string, RequestInit])[1].body as string)).toEqual({ token: "email-token" });
    expect(JSON.parse((fetchMock.mock.calls[5] as [string, RequestInit])[1].body as string)).toEqual({ confirmation: "DELETE" });
    for (const index of [1, 3, 5]) {
      expect(new Headers((fetchMock.mock.calls[index] as [string, RequestInit])[1].headers).get("X-CSRF-Token")).toBe("account-csrf");
    }
    expect((fetchMock.mock.calls[1] as [string, RequestInit])[1].body).not.toContain("expected_revision");
  });

  it("turns revision conflicts into typed errors with field details", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: "revision_conflict", message: "Объявление изменилось", field_errors: { expected_revision: "Устарела версия" }, request_id: "req-1" }), { status: 409, headers: { "Content-Type": "application/json" } })));
    await expect(apiRequest("listings/draft-1", { method: "PATCH", body: "{}" })).rejects.toMatchObject({
      name: "ApiClientError",
      status: 409,
      code: "revision_conflict",
      fieldErrors: { expected_revision: "Устарела версия" },
      requestId: "req-1"
    } satisfies Partial<ApiClientError>);
  });

  it("sends expected revisions when changing company details or moderation state", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ company: { id: "company-1" } }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ company: { id: "company-1" } }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    setCsrfToken("session-csrf");

    await api.updateCompany("company-1", 4, { name: "Компания", unp: "123456789", address: "Минск, улица 1", phone: "+375291234567" });
    await api.moderateCompany("company-1", "approve", 4);

    expect(JSON.parse((fetchMock.mock.calls[0] as [string, RequestInit])[1].body as string)).toEqual({
      name: "Компания", unp: "123456789", address: "Минск, улица 1", phone: "+375291234567", expected_revision: 4
    });
    expect(JSON.parse((fetchMock.mock.calls[1] as [string, RequestInit])[1].body as string)).toEqual({ expected_revision: 4 });
  });

  it("loads notification inboxes and marks one item read", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [], unread_count: 0 }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    setCsrfToken("session-csrf");

    await api.notifications({ unreadOnly: true, limit: 25 });
    await api.markNotificationRead("notification/1");

    expect((fetchMock.mock.calls[0] as [string, RequestInit])[0]).toBe("/api/v1/me/notifications?unread_only=true&limit=25");
    expect((fetchMock.mock.calls[1] as [string, RequestInit])[0]).toBe("/api/v1/me/notifications/notification%2F1/read");
    expect(new Headers((fetchMock.mock.calls[1] as [string, RequestInit])[1].headers).get("X-CSRF-Token")).toBe("session-csrf");
  });

  it("uses the revision-protected global notification preference and phone change contracts", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ preferences: { web_enabled: true, email_enabled: false, revision: 4, email_verified: false } }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ preferences: { web_enabled: false, email_enabled: true, revision: 5, email_verified: true } }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ accepted: true, challenge_id: "challenge-1", old_phone_masked: "+375 ** ***-**-67", new_phone_masked: "+375 ** ***-**-12", expires_in_seconds: 600 }), { status: 202, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ changed: true }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    setCsrfToken("session-csrf");

    await api.notificationPreferences();
    await api.updateNotificationPreferences({ web_enabled: false, email_enabled: true, expected_revision: 4 });
    await api.requestPhoneChange("+375291234512");
    await api.confirmPhoneChange("challenge-1", "123456", "654321");

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/v1/me/notification-preferences", "/api/v1/me/notification-preferences",
      "/api/v1/me/profile/phone-change/request", "/api/v1/me/profile/phone-change/confirm"
    ]);
    expect(JSON.parse((fetchMock.mock.calls[1] as [string, RequestInit])[1].body as string)).toEqual({ web_enabled: false, email_enabled: true, expected_revision: 4 });
    expect(JSON.parse((fetchMock.mock.calls[2] as [string, RequestInit])[1].body as string)).toEqual({ phone: "+375291234512" });
    expect(JSON.parse((fetchMock.mock.calls[3] as [string, RequestInit])[1].body as string)).toEqual({ challenge_id: "challenge-1", old_code: "123456", new_code: "654321" });
    for (const index of [1, 2, 3]) expect(new Headers((fetchMock.mock.calls[index] as [string, RequestInit])[1].headers).get("X-CSRF-Token")).toBe("session-csrf");
  });

  it("preserves repeated equipment filters and keeps checkout requests idempotent", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [], pagination: { page: 1, page_size: 25, total: 0, pages: 0 } }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ order: { id: "order-1" }, checkout_url: null }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ colors: [], customs_statuses: [], technical_conditions: [], body_conditions: [], equipment: [] }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    setCsrfToken("session-csrf");

    await api.listings({ equipment: ["abs", "rear_camera"], has_vin: "true", color: "blue" });
    await api.createBillingOrder({ tariff_id: "tariff-1", listing_id: "listing-1", company_id: null }, "order-key-1");
    await api.listingOptions();

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/v1/listings?equipment=abs&equipment=rear_camera&has_vin=true&color=blue",
      "/api/v1/billing/orders", "/api/v1/listing-options"
    ]);
    const orderInit = (fetchMock.mock.calls[1] as [string, RequestInit])[1];
    expect(JSON.parse(orderInit.body as string)).toEqual({ tariff_id: "tariff-1", listing_id: "listing-1", company_id: null });
    expect(new Headers(orderInit.headers).get("Idempotency-Key")).toBe("order-key-1");
    expect(new Headers(orderInit.headers).get("X-CSRF-Token")).toBe("session-csrf");
  });

  it("uses the conversation endpoints and includes CSRF tokens on every write", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [] }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ conversation: { id: "thread-1" } }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ conversation: { id: "thread-1" }, messages: [] }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ message: { id: "message-1" } }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    setCsrfToken("session-csrf");

    await api.conversations();
    await api.createConversation("listing-1", "Здравствуйте", "create-key");
    await api.conversation("thread/1");
    await api.sendConversationMessage("thread/1", "Спасибо", "send-key");
    await api.markConversationRead("thread/1", "read-key");
    await api.blockConversation("thread/1", "block-key");

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/v1/conversations",
      "/api/v1/conversations",
      "/api/v1/conversations/thread%2F1",
      "/api/v1/conversations/thread%2F1/messages",
      "/api/v1/conversations/thread%2F1/read",
      "/api/v1/conversations/thread%2F1/block"
    ]);
    expect(JSON.parse((fetchMock.mock.calls[1] as [string, RequestInit])[1].body as string)).toEqual({ listing_id: "listing-1", message: "Здравствуйте" });
    expect(JSON.parse((fetchMock.mock.calls[3] as [string, RequestInit])[1].body as string)).toEqual({ message: "Спасибо" });
    for (const [callIndex, expectedKey] of [[1, "create-key"], [3, "send-key"], [4, "read-key"], [5, "block-key"]] as const) {
      const init = (fetchMock.mock.calls[callIndex] as [string, RequestInit])[1];
      expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("session-csrf");
      expect(new Headers(init.headers).get("Idempotency-Key")).toBe(expectedKey);
    }
  });

  it("requests conversation history with a bounded sequence cursor", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ conversation: {}, messages: [], has_more: true, next_before_sequence: 40 }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await api.conversation("thread/1", { beforeSequence: 40, limit: 20 });

    expect((fetchMock.mock.calls[0] as [string, RequestInit])[0]).toBe("/api/v1/conversations/thread%2F1?limit=20&before_sequence=40");
  });

  it("requests listing counts with the same repeated filters as search", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ total: 1234 }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await api.listingCount({ make_id: "make-1", equipment: ["abs", "esp"], page: "3", sort: "newest" });

    expect((fetchMock.mock.calls[0] as [string, RequestInit])[0]).toBe("/api/v1/listings/count?make_id=make-1&equipment=abs&equipment=esp&page=3&sort=newest");
  });

  it("mints idempotency keys when conversation actions do not provide one", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    setCsrfToken("session-csrf");

    await api.createConversation("listing-1", "Здравствуйте");
    await api.sendConversationMessage("thread-1", "Спасибо");
    await api.markConversationRead("thread-1");
    await api.blockConversation("thread-1");

    const keys = fetchMock.mock.calls.map(([, init]) => new Headers((init as RequestInit).headers).get("Idempotency-Key"));
    expect(keys.every(Boolean)).toBe(true);
    expect(new Set(keys).size).toBe(4);
  });
});
