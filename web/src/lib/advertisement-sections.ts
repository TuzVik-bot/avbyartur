/** Public navigation order matches the advertised marketplace sections. */
export const advertisementSections = [
  { label: "Авто с пробегом", href: "/cars?category_code=cars&condition=used" },
  { label: "Электромобили", href: "/cars?category_code=cars&fuel=electric" },
  { label: "Новые авто", href: "/cars?category_code=cars&condition=new" },
  { label: "Мототехника", href: "/motorcycles" },
  { label: "Сельхозтехника", href: "/agricultural-equipment" },
  { label: "Грузовики", href: "/trucks" },
  { label: "Прицепы", href: "/trailers" },
  { label: "Водный транспорт", href: "/watercraft" },
  { label: "Спецтехника", href: "/special-equipment" },
  { label: "Автобусы", href: "/buses" },
  { label: "Запчасти и автотовары", href: "/parts" },
  { label: "Шины и диски", href: "/tires-and-wheels" },
  { label: "Услуги", href: "/services" }
] as const;
