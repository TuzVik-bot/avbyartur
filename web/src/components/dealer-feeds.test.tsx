import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { dealerTeamApi, type DealerFeed, type DealerFeedImportRow, type DealerFeedImportRun, type DealerFeedMissingCandidate, type DealerTeamMember } from "@/lib/dealer";
import { DealerFeeds } from "@/components/dealer-feeds";

const owner: DealerTeamMember = {
  id: "owner-row", user_id: "owner-user", email: "owner@example.test", display_name: "Владелец",
  role: "owner", status: "active", revision: 1, created_at: "2026-10-01T10:00:00Z"
};
const feed: DealerFeed = {
  id: "feed-1", name: "Каталог", format: "csv", status: "active", field_mapping: {}, api_token_prefix: null,
  manual_conflict_policy: "review", missing_retirement_enabled: false, missing_retirement_delay_hours: 168,
  created_at: "2026-10-01T10:00:00Z", latest_import: null, last_successful_import_at: null,
  last_successful_import_age_seconds: null
};
const candidate: DealerFeedMissingCandidate = {
  dealer_external_id: "STOCK-100", listing_id: "listing-1", title: "Toyota Camry", status: "active",
  listing_revision: 4, expected_listing_revision: 4, snapshot_digest: "a".repeat(64),
  missing_since: "2026-09-30T10:00:00Z", due_at: "2026-09-30T11:00:00Z", eligible: true, reason: null
};
const run = (dry_run: boolean): DealerFeedImportRun => ({
  id: dry_run ? "preview-run" : "applied-run", feed_id: feed.id, status: dry_run ? "preview" : "succeeded", dry_run,
  source_filename: "stock.csv", total_rows: 1, applied_rows: dry_run ? 0 : 1, rejected_rows: 0,
  error_code: null, created_at: "2026-10-01T10:00:00Z", completed_at: "2026-10-01T10:00:01Z"
});

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  container = document.createElement("div");
  document.body.append(container);
  act(() => { root = createRoot(container); });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

async function render() {
  await act(async () => {
    root.render(createElement(DealerFeeds, { initialFeeds: [feed], initialTeam: [owner], currentUserId: owner.user_id }));
  });
}

describe("dealer feeds", () => {
  it("shows empty import and successful-application states for a new source", async () => {
    vi.spyOn(dealerTeamApi, "importHistory").mockResolvedValue({ items: [], next_cursor: null });
    await render();

    expect(container.textContent).toContain("Импортов ещё не было.");
    expect(container.textContent).toContain("Успешных применений ещё не было.");
  });

  it("shows the latest applied result and the age of the last full success per source", async () => {
    const lastAttempt = {
      ...run(false),
      id: "partial-run",
      status: "partial" as const,
      source_filename: "partial.csv",
      total_rows: 3,
      applied_rows: 2,
      rejected_rows: 1,
      created_at: "2026-10-21T09:15:00Z"
    };
    const feedWithFreshness = {
      ...feed,
      latest_import: lastAttempt,
      last_successful_import_at: "2026-10-21T08:00:00Z",
      last_successful_import_age_seconds: 7200
    } as DealerFeed;
    vi.spyOn(dealerTeamApi, "importHistory").mockResolvedValue({ items: [], next_cursor: null });

    await act(async () => {
      root.render(createElement(DealerFeeds, {
        initialFeeds: [feedWithFreshness], initialTeam: [owner], currentUserId: owner.user_id
      }));
    });

    expect(container.textContent).toContain("Последний импорт");
    expect(container.textContent).toContain("Частично");
    expect(container.textContent).toContain("partial.csv");
    expect(container.textContent).toContain("2 ч");
  });

  it("refreshes per-source freshness after applying a file", async () => {
    const applied = { ...run(false), id: "fresh-run", source_filename: "stock.csv" };
    const updatedFeed = {
      ...feed,
      latest_import: applied,
      last_successful_import_at: applied.completed_at,
      last_successful_import_age_seconds: 0
    } as DealerFeed;
    const importCall = vi.spyOn(dealerTeamApi, "importFeedFile").mockResolvedValue({ run: applied, missing_candidates: [] });
    const rowsCall = vi.spyOn(dealerTeamApi, "importRows").mockResolvedValue({ items: [] });
    const historyCall = vi.spyOn(dealerTeamApi, "importHistory").mockResolvedValue({ items: [], next_cursor: null });
    const feedsCall = vi.spyOn(dealerTeamApi, "feeds").mockResolvedValue({ items: [updatedFeed] });

    await render();
    const fileInput = container.querySelector<HTMLInputElement>('input[type="file"]')!;
    const file = new File(["dealer_external_id,title\nSTOCK-100,Toyota Camry"], "stock.csv", { type: "text/csv" });
    Object.defineProperty(fileInput, "files", { configurable: true, value: [file] });
    await act(async () => { fileInput.dispatchEvent(new Event("change", { bubbles: true })); });
    const applyButton = [...container.querySelectorAll<HTMLButtonElement>(".feed-import-actions button")][1];
    await act(async () => { applyButton.click(); await new Promise((resolve) => setTimeout(resolve, 0)); });

    expect(importCall).toHaveBeenCalledWith(feed.id, file, false, expect.any(String), false);
    expect(rowsCall).toHaveBeenCalledWith(applied.id);
    expect(historyCall).toHaveBeenCalledTimes(1);
    expect(feedsCall).toHaveBeenCalledTimes(1);
    expect(container.textContent).toContain("Последний импорт");
    expect(container.textContent).toContain("Успешно");
  });

  it("loads persisted company import history without relying on this browser session", async () => {
    const historicalRun: DealerFeedImportRun = {
      ...run(false), id: "older-run", source_filename: "archived-stock.csv", created_at: "2026-09-29T09:00:00Z"
    };
    const fetchCall = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("dealer/feed-imports?")) {
        return new Response(JSON.stringify({ items: [{ feed_name: "Архивный источник", run: historicalRun }], next_cursor: null }), { status: 200 });
      }
      return new Response(JSON.stringify({ items: [] }), { status: 200 });
    });

    await render();
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });

    expect(fetchCall).toHaveBeenCalledWith(expect.stringContaining("/api/v1/dealer/feed-imports?"), expect.objectContaining({ method: "GET" }));
    expect(container.textContent).toContain("archived-stock.csv");
    expect(container.textContent).toContain("Архивный источник");
  });

  it("shows the draft review path and links applied drafts for review", async () => {
    const appliedRun = {
      ...run(false), id: "draft-run", source_filename: "dealer-stock.csv", status: "partial" as const,
      total_rows: 4, applied_rows: 2, rejected_rows: 1
    };
    const appliedRows: DealerFeedImportRow[] = [
      {
        id: "00000000-0000-4000-8000-000000000001", row_number: 1, dealer_external_id: "STOCK-NEW", listing_id: "00000000-0000-4000-8000-000000000101",
        status: "draft", action: "created", error_code: null, error_message: null, field_errors: {}
      },
      {
        id: "00000000-0000-4000-8000-000000000002", row_number: 2, dealer_external_id: "STOCK-UPDATED", listing_id: "00000000-0000-4000-8000-000000000102",
        status: "draft", action: "updated", error_code: null, error_message: null, field_errors: {}
      },
      {
        id: "00000000-0000-4000-8000-000000000003", row_number: 3, dealer_external_id: "STOCK-UNCHANGED", listing_id: "00000000-0000-4000-8000-000000000103",
        status: "unchanged", action: "unchanged", error_code: null, error_message: null, field_errors: {}
      },
      {
        id: "00000000-0000-4000-8000-000000000004", row_number: 4, dealer_external_id: "STOCK-REJECTED", listing_id: null,
        status: "rejected", action: null, error_code: "invalid_year", error_message: "Invalid year", field_errors: { year: "Invalid year" }
      }
    ];
    vi.spyOn(dealerTeamApi, "importHistory").mockResolvedValue({
      items: [{ feed_name: feed.name, run: appliedRun }], next_cursor: null
    });
    const rowsCall = vi.spyOn(dealerTeamApi, "importRows").mockResolvedValue({ items: appliedRows });

    await render();
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
    expect(container.textContent).toContain("Новые и изменённые записи после успешного применения становятся черновиками");
    expect(container.textContent).toContain("владелец, администратор или продавец проверяет карточку и отправляет её на модерацию");
    expect(container.textContent).toContain("Неизменённые объявления сохраняют статус; отклонённые строки не применяются.");
    expect(container.textContent).toContain("Изменение активного объявления возвращает его в черновики");

    await act(async () => {
      container.querySelector<HTMLButtonElement>(".feed-run-button")!.click();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(rowsCall).toHaveBeenCalledWith(appliedRun.id);
    expect(container.querySelector<HTMLAnchorElement>('a[href="/sell?listing=00000000-0000-4000-8000-000000000101"]')?.textContent).toBe("Открыть объявление");
    expect(container.querySelector<HTMLAnchorElement>('a[href="/sell?listing=00000000-0000-4000-8000-000000000102"]')?.textContent).toBe("Открыть объявление");
    expect(container.querySelector('a[href="/sell?listing=00000000-0000-4000-8000-000000000103"]')).toBeNull();
    expect(container.textContent).toContain("Без изменений; статус объявления сохранён.");
    expect(container.textContent).toContain("Отклонено; объявление не изменено.");
    expect(container.textContent).toContain("После обновления объявление находится в черновиках. Проверьте изменения и отправьте его на модерацию.");
    expect(container.textContent).toContain("Редактирование и отправка доступны владельцу, администратору или продавцу компании.");
  });

  it("retries selected import rows without reloading the history list", async () => {
    const historicalRun: DealerFeedImportRun = {
      ...run(false), id: "older-run", source_filename: "archived-stock.csv", created_at: "2026-09-29T09:00:00Z"
    };
    const historyCall = vi.spyOn(dealerTeamApi, "importHistory").mockResolvedValue({
      items: [{ feed_name: "Архивный источник", run: historicalRun }], next_cursor: null
    });
    const rowsCall = vi.spyOn(dealerTeamApi, "importRows")
      .mockRejectedValueOnce(new Error("temporary rows failure"))
      .mockResolvedValueOnce({ items: [] });

    await render();
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
    await act(async () => {
      container.querySelector<HTMLButtonElement>(".feed-run-button")!.click();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(container.querySelector('[role="alert"]')?.textContent).toContain("Повторить загрузку строк");
    await act(async () => {
      [...container.querySelectorAll<HTMLButtonElement>("button")].find((button) => button.textContent?.includes("Повторить загрузку строк"))!.click();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(rowsCall).toHaveBeenCalledTimes(2);
    expect(historyCall).toHaveBeenCalledTimes(1);
    expect(container.textContent).toContain("Ошибок строк нет.");
  });

  it("does not show an empty history state when loading the history fails", async () => {
    const historyCall = vi.spyOn(dealerTeamApi, "importHistory")
      .mockRejectedValueOnce(new Error("temporary history failure"))
      .mockResolvedValueOnce({ items: [], next_cursor: null });

    await render();
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
    expect(container.textContent).not.toContain("Импортов пока нет.");

    await act(async () => {
      [...container.querySelectorAll<HTMLButtonElement>("button")].find((button) => button.textContent?.includes("Повторить загрузку"))!.click();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(historyCall).toHaveBeenCalledTimes(2);
    expect(container.textContent).toContain("Импортов пока нет.");
  });

  it("runs a preview and an apply with separate idempotency keys and displays history", async () => {
    await render();
    const importCall = vi.spyOn(dealerTeamApi, "importFeedFile")
      .mockResolvedValueOnce({ run: run(true), missing_candidates: [] })
      .mockResolvedValueOnce({ run: run(false), missing_candidates: [] });
    vi.spyOn(dealerTeamApi, "importRun").mockImplementation(async (id) => ({ run: run(id === "preview-run") }));
    vi.spyOn(dealerTeamApi, "importRows").mockResolvedValue({ items: [] });
    const fileInput = container.querySelector<HTMLInputElement>('input[type="file"]')!;
    const file = new File(["id,make\n1,Toyota"], "stock.csv", { type: "text/csv" });
    Object.defineProperty(fileInput, "files", { configurable: true, value: [file] });
    await act(async () => { fileInput.dispatchEvent(new Event("change", { bubbles: true })); });
    const buttons = [...container.querySelectorAll<HTMLButtonElement>(".feed-import-actions button")];
    await act(async () => { buttons[0].click(); await new Promise((resolve) => setTimeout(resolve, 0)); });
    await act(async () => { buttons[1].click(); await new Promise((resolve) => setTimeout(resolve, 0)); });
    expect(importCall).toHaveBeenNthCalledWith(1, feed.id, file, true, expect.any(String), false);
    expect(importCall).toHaveBeenNthCalledWith(2, feed.id, file, false, expect.any(String), false);
    expect(importCall.mock.calls[0][3]).not.toBe(importCall.mock.calls[1][3]);
    expect(container.textContent).toContain("применён");
    expect(container.textContent).toContain("История импортов");
  });

  it("does not expose file import or creation to viewers", async () => {
    await act(async () => {
      root.render(createElement(DealerFeeds, {
        initialFeeds: [feed], initialTeam: [{ ...owner, role: "viewer", user_id: "viewer-user" }], currentUserId: "viewer-user"
      }));
    });
    expect(container.querySelector(".dealer-feed-create")).toBeNull();
    expect(container.querySelector('input[type="file"]')).toBeNull();
    expect(container.textContent).toContain("доступен просмотр");
  });

  it("lets sellers import and read candidates without feed management or pause confirmation", async () => {
    await act(async () => {
      root.render(createElement(DealerFeeds, {
        initialFeeds: [feed], initialTeam: [{ ...owner, role: "seller", user_id: "seller-user" }], currentUserId: "seller-user"
      }));
    });
    vi.spyOn(dealerTeamApi, "missingCandidates").mockResolvedValue({ items: [candidate] });
    expect(container.querySelector(".dealer-feed-create")).toBeNull();
    expect(container.querySelector(".feed-policy")).toBeNull();
    expect(container.querySelector('input[type="file"]')).not.toBeNull();
    await act(async () => { container.querySelector<HTMLButtonElement>(".feed-candidates button")!.click(); await new Promise((resolve) => setTimeout(resolve, 0)); });
    expect(container.textContent).toContain("STOCK-100");
    expect(container.textContent).not.toContain("Подтвердить паузу");
  });

  it("saves feed policy, previews complete snapshots, and confirms an eligible candidate", async () => {
    await render();
    const policyCall = vi.spyOn(dealerTeamApi, "updateFeedPolicy").mockResolvedValue({
      feed: { ...feed, manual_conflict_policy: "feed_wins", missing_retirement_enabled: true, missing_retirement_delay_hours: 24 },
      api_token: null
    });
    const snapshotPreview = vi.spyOn(dealerTeamApi, "importFeedFile").mockResolvedValue({ run: run(true), missing_candidates: [candidate] });
    vi.spyOn(dealerTeamApi, "importRun").mockResolvedValue({ run: run(true) });
    vi.spyOn(dealerTeamApi, "importRows").mockResolvedValue({ items: [] });
    vi.spyOn(dealerTeamApi, "missingCandidates").mockResolvedValue({ items: [candidate] });
    const confirmationCall = vi.spyOn(dealerTeamApi, "confirmMissingCandidate").mockResolvedValue({ run: run(false), paused_external_ids: [candidate.dealer_external_id] });

    const selects = container.querySelectorAll<HTMLSelectElement>(".feed-policy select");
    await act(async () => {
      selects[0].value = "feed_wins";
      selects[0].dispatchEvent(new Event("change", { bubbles: true }));
    });
    const delayInput = container.querySelector<HTMLInputElement>(".feed-policy input[type='number']")!;
    const setInputValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    await act(async () => {
      setInputValue?.call(delayInput, "24");
      delayInput.dispatchEvent(new Event("input", { bubbles: true }));
      delayInput.dispatchEvent(new Event("change", { bubbles: true }));
    });
    const retirementToggle = container.querySelector<HTMLInputElement>(".feed-policy input[type='checkbox']")!;
    await act(async () => { retirementToggle.click(); });
    await act(async () => { container.querySelector<HTMLButtonElement>(".feed-policy button")!.click(); await new Promise((resolve) => setTimeout(resolve, 0)); });
    expect(policyCall).toHaveBeenCalledWith(feed.id, {
      manual_conflict_policy: "feed_wins", missing_retirement_enabled: true, missing_retirement_delay_hours: 24
    });

    const fileInput = container.querySelector<HTMLInputElement>('input[type="file"]')!;
    const file = new File(["dealer_external_id,title\nSTOCK-100,Toyota Camry"], "stock.csv", { type: "text/csv" });
    Object.defineProperty(fileInput, "files", { configurable: true, value: [file] });
    await act(async () => { fileInput.dispatchEvent(new Event("change", { bubbles: true })); });
    const snapshotToggle = [...container.querySelectorAll<HTMLInputElement>(".feed-file-import input[type='checkbox']")][0];
    await act(async () => { snapshotToggle.click(); });
    const previewButton = [...container.querySelectorAll<HTMLButtonElement>(".feed-import-actions button")][0];
    await act(async () => { previewButton.click(); await new Promise((resolve) => setTimeout(resolve, 0)); });
    expect(snapshotPreview).toHaveBeenCalledWith(feed.id, file, true, expect.any(String), true);
    expect(container.textContent).toContain("Предпросмотр отсутствующих объявлений");
    expect(container.querySelector('a[href="/api/v1/dealer/feeds/samples/schema"]')).not.toBeNull();

    const checkCandidates = [...container.querySelectorAll<HTMLButtonElement>(".feed-candidates button")].find((button) => button.textContent?.includes("Проверить список"))!;
    await act(async () => { checkCandidates.click(); await new Promise((resolve) => setTimeout(resolve, 0)); });
    const confirmButton = [...container.querySelectorAll<HTMLButtonElement>(".feed-candidates button")].find((button) => button.textContent?.includes("Подтвердить паузу"))!;
    await act(async () => { confirmButton.click(); await new Promise((resolve) => setTimeout(resolve, 0)); });
    expect(confirmationCall).toHaveBeenCalledWith(feed.id, {
      dealer_external_id: candidate.dealer_external_id,
      expected_listing_revision: candidate.expected_listing_revision,
      snapshot_digest: candidate.snapshot_digest
    }, expect.any(String));
  });
});
