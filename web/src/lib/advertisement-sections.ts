/** Public navigation order matches the advertised marketplace sections. */
export const advertisementSections = [
  { label: "Авто с пробегом", href: "/cars?category_code=cars&condition=used" },
  { label: "Электромобили", href: "/cars?category_code=cars&fuel=electric" },
  { label: "Новые авто", href: "/cars?category_code=cars&condition=new" },
  { label: "Мототехника", href: "/cars?category_code=motorcycles" },
  { label: "Сельхозтехника", href: "/cars?category_code=agricultural_equipment" },
  { label: "Грузовики", href: "/cars?category_code=trucks" },
  { label: "Прицепы", href: "/cars?category_code=trailers" },
  { label: "Водный транспорт", href: "/cars?category_code=watercraft" },
  { label: "Спецтехника", href: "/cars?category_code=special_equipment" },
  { label: "Автобусы", href: "/cars?category_code=buses" },
  { label: "Запчасти и автотовары", href: "/cars?category_code=parts" },
  { label: "Шины и диски", href: "/tires-and-wheels" },
  { label: "Услуги", href: "/services" }
] as const;
