import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { FeedImportHistory, type FeedImportDetail } from "@/components/feed-import-history";
import type { DealerFeedImportRun } from "@/lib/dealer";

function failedRun(errorCode: string): FeedImportDetail {
  const run = {
    id: "run-1", feed_id: "feed-1", source_filename: "cars.csv", status: "failed", dry_run: true,
    total_rows: 0, applied_rows: 0, rejected_rows: 0, error_code: errorCode, created_at: "2026-11-10T10:00:00Z"
  } as unknown as DealerFeedImportRun;
  return { feed_name: "Склад", run, rows: [] };
}

function render(detail: FeedImportDetail) {
  const noop = () => undefined;
  return renderToStaticMarkup(createElement(FeedImportHistory, {
    items: [detail], selectedId: detail.run.id, onSelect: noop, nextCursor: null, loading: false, error: "",
    onLoadMore: noop, onRetry: noop, selectedRowsLoading: false, selectedRowsError: "", onRetrySelectedRows: noop
  }));
}

describe("feed import history run errors", () => {
  it("explains an invalid file encoding in Russian instead of showing the code", () => {
    const html = render(failedRun("invalid_encoding"));

    expect(html).toContain("Файл должен быть в кодировке UTF-8 или Windows-1251");
    expect(html).not.toContain("invalid_encoding");
  });

  it("keeps an unknown processing error code visible for support", () => {
    expect(render(failedRun("some_new_code"))).toContain("Ошибка обработки: some_new_code");
  });
});
