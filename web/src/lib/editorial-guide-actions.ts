import type { EditorialArticle } from "@/lib/editorial-articles";

export type EditorialGuideAction = {
  href: string;
  label: string;
  description: string;
};

export const editorialGuideActions: Record<EditorialArticle["slug"], readonly EditorialGuideAction[]> = {
  "pokupka-avtomobilya-s-probegom": [
    {
      href: "/useful-information#use-case-presets-title",
      label: "Настроить подборку по задаче",
      description: "Выберите сценарий и измените фильтры перед переходом к объявлениям.",
    },
    {
      href: "/cars?category_code=cars&condition=used",
      label: "Смотреть объявления с пробегом",
      description: "Перейдите к актуальной выдаче легковых автомобилей с пробегом.",
    },
  ],
  "podgotovka-avtomobilya-k-prodazhe": [
    {
      href: "/cars?category_code=cars&condition=used",
      label: "Открыть объявления с пробегом",
      description: "Выберите похожие варианты и сопоставьте модель, год, комплектацию, пробег и состояние.",
    },
    {
      href: "/sell",
      label: "Создать объявление",
      description: "Перейдите к началу размещения своего автомобиля.",
    },
  ],
  "kak-vybrat-avtoservis": [
    {
      href: "/services",
      label: "Найти автосервис",
      description: "Откройте каталог и уточните у выбранной мастерской, выполняет ли она нужную работу.",
    },
  ],
};

export const editorialContentUpdated = "22 октября 2026";
