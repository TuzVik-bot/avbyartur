export type ListingQualityStatus = "complete" | "missing" | "not_checked";
export type ListingQualityTarget = { fieldId: string; step: number };
export type ListingQualityCheck = {
  id: string;
  kind: "required" | "recommended";
  label: string;
  status: ListingQualityStatus;
  detail: string;
  target?: ListingQualityTarget;
};

type CategoryRequirements = { top_level?: readonly string[]; category_details?: readonly string[] };

export type ListingQualityInput = {
  categoryCode: string;
  requirements?: CategoryRequirements;
  values: Readonly<Record<string, string>>;
  targets: Readonly<Record<string, ListingQualityTarget | undefined>>;
  readyPhotoCount: number;
  minimumPhotoCount: number | null;
};

export type ListingQuality = {
  required: ListingQualityCheck[];
  recommended: ListingQualityCheck[];
  photoAdvice: readonly string[];
};

const topLevelLabels: Record<string, string> = {
  make: "марку",
  model: "модель",
  year: "год выпуска",
  mileage_km: "пробег",
  fuel: "тип топлива",
  transmission: "коробку передач",
  drive: "привод"
};

const categoryDetailLabels: Record<string, string> = {
  vehicle_type: "тип техники",
  payload_kg: "грузоподъёмность",
  gross_weight_kg: "полную массу",
  axle_configuration: "колёсную формулу",
  seats: "число мест",
  engine_type: "тип двигателя",
  engine_volume_cc: "объём двигателя",
  power_hp: "мощность",
  equipment_type: "тип оборудования",
  operating_hours: "наработку в часах",
  weight_kg: "массу",
  working_width_m: "рабочую ширину",
  trailer_type: "тип прицепа",
  axles: "число осей",
  watercraft_type: "тип судна",
  length_m: "длину судна",
  hull_material: "материал корпуса",
  motor_power_hp: "мощность двигателя",
  part_group: "группу запчасти",
  diameter_in: "диаметр",
  width_in: "ширину",
  bolt_holes: "число крепёжных отверстий",
  pcd_mm: "разболтовку",
  profile_percent: "профиль шины",
  season: "сезонность",
  manufacturer: "производителя",
  part_number: "артикул",
  compatibility: "совместимость",
  quantity: "количество",
  offset_et: "вылет ET",
  dia_mm: "диаметр ступичного отверстия",
  material: "материал",
  load_index: "индекс нагрузки",
  speed_index: "индекс скорости"
};

const photoAdviceByCategory: Record<string, readonly string[]> = {
  cars: ["Покажите автомобиль спереди, сзади и с обоих боков.", "Добавьте салон, приборную панель и заметные повреждения."],
  trucks: ["Снимите технику целиком с нескольких сторон и отдельно кабину.", "Покажите кузов или надстройку, шильдик и следы износа."],
  buses: ["Добавьте общий вид автобуса с разных сторон и салон.", "Покажите место водителя, приборы и состояние сидений."],
  motorcycles: ["Снимите мотоцикл целиком с обеих сторон.", "Добавьте приборную панель, двигатель и видимые повреждения."],
  special_equipment: ["Покажите технику целиком и рабочее оборудование.", "Добавьте приборы наработки и изношенные узлы."],
  agricultural_equipment: ["Покажите технику целиком и рабочие узлы.", "Добавьте маркировку и состояние навесного оборудования."],
  trailers: ["Снимите прицеп с обоих боков и сзади.", "Покажите сцепное устройство, оси и маркировку."],
  watercraft: ["Покажите судно с обоих бортов и палубу.", "Добавьте корпус, двигатель и заметные дефекты."],
  parts: ["Снимите деталь с нескольких сторон.", "Покажите маркировку, комплектность и дефекты."],
  wheels: ["Снимите колесо целиком и крупно маркировку.", "Покажите крепёжную сторону и состояние диска."],
  tires: ["Покажите протектор крупным планом и боковину.", "Снимите маркировку размера и видимые повреждения."]
};
const genericPhotoAdvice = ["Покажите предмет целиком с нескольких сторон.", "Добавьте крупный план маркировки, комплектности и видимых дефектов."];

function present(value: string | undefined) {
  return Boolean(value?.trim());
}

function humanizeField(field: string) {
  return categoryDetailLabels[field] || field.replace(/_/g, " ");
}

export function buildListingQuality(input: ListingQualityInput): ListingQuality {
  const required: ListingQualityCheck[] = [];
  const recommended: ListingQualityCheck[] = [];

  const titleReady = present(input.values.title);
  const requiredTopLevel = [...(input.requirements?.top_level || [])];
  const missingTopLevel = requiredTopLevel.filter((field) => !present(input.values[field]));
  const missingIdentity = !titleReady;
  const identityMissing = [
    ...(missingIdentity ? ["название объявления"] : []),
    ...missingTopLevel.map((field) => topLevelLabels[field] || humanizeField(field))
  ];
  const firstMissingIdentityField = missingIdentity ? "make" : missingTopLevel[0];
  required.push({
    id: "identity",
    kind: "required",
    label: "Название и основные характеристики",
    status: identityMissing.length ? "missing" : "complete",
    detail: identityMissing.length ? `Не указано: ${identityMissing.join(", ")}.` : "Заполнено.",
    target: firstMissingIdentityField ? input.targets[firstMissingIdentityField] : undefined
  });

  required.push({
    id: "condition",
    kind: "required",
    label: "Состояние",
    status: present(input.values.condition) ? "complete" : "missing",
    detail: present(input.values.condition) ? "Указано." : "Не выбрано.",
    target: input.values.condition ? undefined : input.targets.condition
  });
  required.push({
    id: "description",
    kind: "required",
    label: "Описание",
    status: present(input.values.description) ? "complete" : "missing",
    detail: present(input.values.description) ? "Добавлено." : "Не добавлено.",
    target: input.values.description ? undefined : input.targets.description
  });
  required.push({
    id: "price",
    kind: "required",
    label: "Цена",
    status: present(input.values.price) && Number(input.values.price) > 0 ? "complete" : "missing",
    detail: present(input.values.price) && Number(input.values.price) > 0 ? "Указана." : "Не указана.",
    target: present(input.values.price) ? undefined : input.targets.price
  });
  const hasLocation = present(input.values.region) && present(input.values.city);
  required.push({
    id: "location",
    kind: "required",
    label: "Место продажи",
    status: hasLocation ? "complete" : "missing",
    detail: hasLocation ? "Область и населённый пункт указаны." : "Укажите область и населённый пункт.",
    target: !present(input.values.region) ? input.targets.region : input.targets.city
  });
  required.push({
    id: "contact",
    kind: "required",
    label: "Телефон для связи",
    status: present(input.values.contact_phone) ? "complete" : "missing",
    detail: present(input.values.contact_phone) ? "Указан." : "Не указан.",
    target: input.values.contact_phone ? undefined : input.targets.contact_phone
  });
  required.push({
    id: "photos",
    kind: "required",
    label: "Обработанные фотографии",
    status: input.minimumPhotoCount === null ? "not_checked" : input.readyPhotoCount >= input.minimumPhotoCount ? "complete" : "missing",
    detail: input.minimumPhotoCount === null
      ? "Правила подачи фото не загружены."
      : `${input.readyPhotoCount} из ${input.minimumPhotoCount} необходимых обработано.`,
    target: input.minimumPhotoCount !== null && input.readyPhotoCount >= input.minimumPhotoCount ? undefined : input.targets.photos
  });

  const requiredCategoryDetails = [...(input.requirements?.category_details || [])];
  if (requiredCategoryDetails.length) {
    required.push({
      id: "category-details",
      kind: "required",
      label: "Характеристики категории",
      status: "not_checked",
      detail: `По правилам подачи нужны: ${requiredCategoryDetails.map(humanizeField).join(", ")}. Эта форма не проверяет и не редактирует эти поля.`
    });
  }

  if (input.categoryCode === "cars") {
    const carRecommendations = [
      ["engine_volume_l", "Объём двигателя"],
      ["power_hp", "Мощность двигателя"],
      ["vin", "VIN"]
    ] as const;
    for (const [field, label] of carRecommendations) {
      recommended.push({
        id: field,
        kind: "recommended",
        label,
        status: present(input.values[field]) ? "complete" : "missing",
        detail: present(input.values[field]) ? "Указано." : "Можно добавить, если данные известны.",
        target: present(input.values[field]) ? undefined : input.targets[field]
      });
    }
  }

  return { required, recommended, photoAdvice: photoAdviceByCategory[input.categoryCode] || genericPhotoAdvice };
}
