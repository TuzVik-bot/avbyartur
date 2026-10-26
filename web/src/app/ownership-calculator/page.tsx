import type { Metadata } from "next";
import { InformationalPage } from "@/components/informational-page";
import { OwnershipCalculator } from "@/components/ownership-calculator";
import { ownershipNeedsCurrentRate, ownershipSeedFromListing, parseOwnershipListingId, type OwnershipCustomsRates } from "@/lib/ownership-listing";
import { serverApi } from "@/lib/server-api";
import type { Listing } from "@/lib/types";
import { buildOpenGraph } from "@/lib/seo";
import { siteUrl } from "@/lib/site-config";

const description = "Оцените расходы на владение автомобилем по вашим данным: топливо или электричество, обслуживание, ремонт и кредит.";
export const metadata: Metadata = {
  title: "Калькулятор стоимости владения автомобилем",
  description,
  alternates: { canonical: siteUrl("/ownership-calculator") },
  openGraph: buildOpenGraph({ title: "Калькулятор стоимости владения автомобилем", description, path: "/ownership-calculator" }),
};

type SearchParams = Record<string, string | string[] | undefined>;
type LoadedListing = { listing: Listing };

function oneId(value: string | string[] | undefined) {
  return typeof value === "string" ? parseOwnershipListingId(value) : null;
}

async function loadListing(id: string): Promise<Listing | null> {
  try {
    const result: LoadedListing = await serverApi.listing(id);
    return result.listing;
  } catch {
    return null;
  }
}

export default async function OwnershipCalculatorPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const requested = [params.listing, params.compare].filter((value) => value !== undefined);
  const ids = requested.map(oneId);
  const notices: string[] = [];
  if (requested.some((_, index) => ids[index] === null)) notices.push("Не удалось распознать ссылку на одно из объявлений. Введите UUID или ссылку на объявление этого сайта; расчёт вручную доступен ниже.");

  const validIds = [...new Set(ids.filter((id): id is string => id !== null))].slice(0, 2);
  const listings = (await Promise.all(validIds.map(loadListing))).filter((listing): listing is Listing => listing !== null);
  if (validIds.length > listings.length) notices.push("Не удалось загрузить одно из публичных объявлений. Вы можете продолжить расчёт вручную.");

  let rates: OwnershipCustomsRates | null = null;
  if (listings.some(ownershipNeedsCurrentRate)) {
    try { rates = await serverApi.customsRates(); }
    catch { notices.push("Текущий официальный курс недоступен. Цена объявления в USD не подставлена в BYN; укажите BYN вручную."); }
  }
  const seeds = listings.map((listing) => ownershipSeedFromListing(listing, rates));
  return (
    <InformationalPage
      eyebrow="Инструменты для автомобилистов"
      title="Стоимость владения автомобилем"
      description="Сравните расходы за выбранный срок и настройте параметры под свои поездки. Значения из объявления отмечены источником; неизвестные характеристики оставлены для ручного ввода."
      notice={notices.length ? notices.join(" ") : undefined}
    >
      <OwnershipCalculator initialVehicles={seeds} />
    </InformationalPage>
  );
}
