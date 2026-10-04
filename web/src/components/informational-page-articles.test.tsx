import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import * as informationalPages from "@/components/informational-page";

const components = informationalPages as unknown as Record<string, unknown>;
const summary = {
  slug: "vin-check-basics", title: "Что показывает VIN-проверка",
  summary: "Как читать результат и какие ограничения учитывать при проверке истории автомобиля.",
  topic: "vin" as const, published_at: "2026-10-04", updated_at: "2026-10-04T10:00:00Z"
};

it("shows published article cards, topic filters and a clear empty state", () => {
  const component = components.UsefulInformationList;
  expect(component).toBeTypeOf("function");
  if (typeof component !== "function") return;

  const html = renderToStaticMarkup(createElement(component as (props: Record<string, unknown>) => React.ReactNode, {
    items: [summary], selectedTopic: "vin"
  }));
  expect(html).toContain("Что показывает VIN-проверка");
  expect(html).toContain("Проверка VIN");
  expect(html).toContain("/useful-information/vin-check-basics");
  expect(html).toContain('aria-current="page"');

  const empty = renderToStaticMarkup(createElement(component as (props: Record<string, unknown>) => React.ReactNode, {
    items: [], selectedTopic: null
  }));
  expect(empty).toContain("Пока нет опубликованных материалов");
});

it("renders the article body as escaped text and provides a safe related-service link", () => {
  const component = components.UsefulInformationArticle;
  expect(component).toBeTypeOf("function");
  if (typeof component !== "function") return;

  const html = renderToStaticMarkup(createElement(component as (props: Record<string, unknown>) => React.ReactNode, {
    article: {
      ...summary, body: "Сверьте идентификаторы.\n\n<script>не исполнять</script>",
      sources: [{ title: "Условия сервиса", url: "https://example.gov.by/terms" }]
    }
  }));
  expect(html).toContain("&lt;script&gt;не исполнять&lt;/script&gt;");
  expect(html).not.toContain("<script>не исполнять</script>");
  expect(html).toContain('href="https://example.gov.by/terms"');
  expect(html).toContain('rel="noopener noreferrer"');
  expect(html).toContain('href="/vin-check"');
});
