import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";
import VinCheckPage, { metadata } from "@/app/vin-check/page";
import { serverApi } from "@/lib/server-api";

vi.mock("@/lib/server-api", () => ({ serverApi: { vinCheckStatus: vi.fn() } }));

it("shows the provider limitation and does not collect a VIN while checks are unavailable", async () => {
  vi.mocked(serverApi.vinCheckStatus).mockResolvedValue({
    available: false,
    provider: null,
    supported_categories: [],
    message: "Поставщик проверки VIN пока не подключён."
  });

  const page = renderToStaticMarkup(await VinCheckPage());

  expect(metadata.robots).toEqual({ index: false, follow: false, noarchive: true, googleBot: { index: false, follow: false, noimageindex: true } });
  expect(page).toContain("Проверка транспорта по VIN");
  expect(page).toContain("Поставщик проверки VIN пока не подключён.");
  expect(page).toContain("VIN для сервиса проверки не принимается и не сохраняется");
  expect(page).not.toContain("<form");
  expect(page).not.toContain('name="vin"');
});
