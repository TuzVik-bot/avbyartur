import type { EditorialArticle } from "@/lib/editorial-articles";

export type EditorialGuideAction = {
  href: string;
  label: string;
  description: string;
};

const tuneSearchActions: readonly EditorialGuideAction[] = [
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
];

const usedSearchActions: readonly EditorialGuideAction[] = [
  {
    href: "/cars?category_code=cars&condition=used",
    label: "Открыть объявления с пробегом",
    description: "Сравните заинтересовавшие модели по цене, пробегу и состоянию.",
  },
  {
    href: "/useful-information#use-case-presets-title",
    label: "Настроить подборку по задаче",
    description: "Выберите сценарий поиска под свою задачу.",
  },
];

const catalogActions: readonly EditorialGuideAction[] = [
  {
    href: "/cars?category_code=cars",
    label: "Открыть каталог автомобилей",
    description: "Посмотрите актуальные объявления и подберите модель под свои задачи.",
  },
  {
    href: "/useful-information#use-case-presets-title",
    label: "Настроить подборку по задаче",
    description: "Выберите сценарий и уточните фильтры перед поиском.",
  },
];

const serviceActions: readonly EditorialGuideAction[] = [
  {
    href: "/services",
    label: "Найти автосервис",
    description: "Откройте каталог и уточните у выбранной мастерской, выполняет ли она нужную работу.",
  },
];

const sellActions: readonly EditorialGuideAction[] = [
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
];

export const editorialGuideActions: Record<EditorialArticle["slug"], readonly EditorialGuideAction[]> = {
  "pokupka-avtomobilya-s-probegom": tuneSearchActions,
  "podgotovka-avtomobilya-k-prodazhe": sellActions,
  "kak-vybrat-avtoservis": serviceActions,
  // Adapted licensed materials from cars.ru.
  "menshe--ne-znachit-luchshe-pochemu-ne-stoit-boyatsya-poderzhannyh-avto-s-bolshim-trassovym-probegom": tuneSearchActions,
  "byudzhetnye-i-vynoslivye-eti-avtomobili-mozhno-pokupat-dazhe-s-probegom-bolee-300-tys-km": usedSearchActions,
  "samostoyatelnaya-proverka-dvigatelya-za-5-minut-kuda-smotret-v-pervuyu-ochered": tuneSearchActions,
  "skolko-avtomobiley-na-vtorichnom-rynke-imeyut-skruchennyy-probeg--otvet-neuteshitelnyy": usedSearchActions,
  "pokupka-avtomobilya-onlayn--est-li-nastoyaschee-i-buduschee-u-etogo-formata-v-rossii": tuneSearchActions,
  "poderzhannye-krossovery-s-vechnymi-avtomatami-top-5-modeley-na-vtorichke": usedSearchActions,
  "eti-mashiny-prakticheski-ne-gniyut-top-5-avtomobiley-kotorym-ne-strashny-gody-i-reagenty": usedSearchActions,
  "hodyat-po-300-tys-km-i-bolshe-top-5-vynoslivyh-krossoverov-s-atmosfernymi-motorami": usedSearchActions,
  "vybiraem-novyj-avtomobil-kitajskogo-brenda": catalogActions,
  "mozhno-brat-top-3-kitayskih-krossoverov-s-horoshim-sootnosheniem-ceny-i-kachestva": catalogActions,
  "kakoe-motornoe-maslo-zalivat-v-kitayskie-avtomobili--ekspert-dal-otvet": serviceActions,
  "skolko-proedet-avtomobil-esli-nikogda-ne-menyat-maslo-v-dvigatele": serviceActions,
  "smotrim-cvet-nyuhaem-a-takzhe-schitaem-motochasy---4-sposoba-opredelit-chto-maslo-v-dvigatele-tochno-pora-menyat": serviceActions,
  "chto-nuzhno-znat-o-pravilnoj-ekspluataczii-avtomobilya": serviceActions,
  "lipuchka-ili-shipy---vybor-zimnih-shin-napryamuyu-zavisit-ot-mesta-ekspluatacii-avtomobilya": serviceActions,
  "top-7-mifov-o-zimnih-shinah": serviceActions,
  "kak-otlichit-poddelnoe-motornoe-maslo-pyat-rabochih-sovetov-kotorye-nelzya-ignorirovat": serviceActions,
  "kak-prodlit-zhizn-turbodizelyu-sem-prostyh-pravil-kotorye-spasut-vash-motor": serviceActions,
  "kak-legko-zavesti-avtomobil-v-lyuboy-moroz-ekspert-rasskazal-to-o-chem-mnogie-ne-znayut": serviceActions,
  "gibrid-ili-dvs-v-2026-sravnenie-zatrat-nadezhnosti-i-ekologii": catalogActions,
  "avtoputeshestvie-po-rossii-kak-podgotovitsya-k-dolgomu-puti-i-sdelat-poezdku-komfortnoj": usedSearchActions,
};

export const editorialContentUpdated = "25 октября 2026";
export const editorialContentUpdatedISO = "2026-10-25";
