import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ListingTrust } from "@/components/listing-trust";

describe("listing trust labels", () => {
  it("labels seller statements and does not imply VIN or history checks without evidence", () => {
    const html = renderToStaticMarkup(createElement(ListingTrust, { claims: [{ label: "Торг", value: "Возможен" }] }));
    expect(html).toContain("Указано продавцом");
    expect(html).toContain("Торг: Возможен");
    expect(html).toContain("нет сведений, подтверждённых независимым источником");
    expect(html).toContain("само по себе не подтверждает историю автомобиля");
  });

  it("renders verification only when source, scope, and date are present", () => {
    const html = renderToStaticMarkup(createElement(ListingTrust, { claims: [], evidence: [
      { label: "Проверка документов", source: "Реестр документов", checked_at: "2026-10-10T12:00:00Z", scope: "документы" },
      { label: "Пустая проверка", source: "", checked_at: "2026-10-10", scope: "VIN" }
    ] }));
    expect(html).toContain("Реестр документов");
    expect(html).toContain("Проверка документов");
    expect(html).not.toContain("Пустая проверка");
  });
});
