import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import UsefulInformationPage from "@/app/useful-information/page";

describe("useful information landing page", () => {
  it("connects existing directories to articles and the four editable search presets", () => {
    const html = renderToStaticMarkup(<UsefulInformationPage />);

    expect(html).toContain("Автосервисы и СТО");
    expect(html).toContain("Статьи и инструкции");
    expect(html).toContain("Подборки по задаче");
    expect(html).toContain("/useful-information/articles");
    expect(html).toContain("Первый автомобиль");
    expect(html).toContain("Для семьи");
    expect(html).toContain("Сравнить электромобили");
    expect(html).toContain("Для работы и перевозок");
    expect(html).toContain("Категория");
    expect(html).toContain("Год выпуска от");
    expect(html).toContain("Цена до, BYN");
  });

  it("opens each preset with an existing, scenario-specific catalog filter", () => {
    const html = renderToStaticMarkup(<UsefulInformationPage />);

    expect(html).toContain('href="/cars?category_code=cars&amp;condition=used"');
    expect(html).toContain('href="/cars?category_code=cars&amp;has_photos=true"');
    expect(html).toContain('href="/cars?category_code=cars&amp;fuel=electric"');
    expect(html).toContain('href="/cars?category_code=trucks"');
  });
});
