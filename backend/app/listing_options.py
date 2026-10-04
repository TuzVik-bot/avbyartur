"""Stable public codes and Russian labels for seller-entered listing options."""

from pydantic import BaseModel, ConfigDict


class ListingOptionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    label: str


class ListingOptionsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    colors: list[ListingOptionOut]
    customs_statuses: list[ListingOptionOut]
    technical_conditions: list[ListingOptionOut]
    body_conditions: list[ListingOptionOut]
    equipment: list[ListingOptionOut]


LISTING_OPTIONS = {
    "colors": [
        {"code": "black", "label": "Чёрный"},
        {"code": "white", "label": "Белый"},
        {"code": "gray", "label": "Серый"},
        {"code": "silver", "label": "Серебристый"},
        {"code": "red", "label": "Красный"},
        {"code": "blue", "label": "Синий"},
        {"code": "green", "label": "Зелёный"},
        {"code": "yellow", "label": "Жёлтый"},
        {"code": "brown", "label": "Коричневый"},
        {"code": "beige", "label": "Бежевый"},
        {"code": "orange", "label": "Оранжевый"},
        {"code": "purple", "label": "Фиолетовый"},
        {"code": "other", "label": "Другой"},
    ],
    "customs_statuses": [
        {"code": "cleared_rb", "label": "Оформлен в РБ (со слов продавца)"},
        {"code": "eaeu_import", "label": "Ввезён из ЕАЭС (со слов продавца)"},
        {"code": "uncleared", "label": "Не растаможен (со слов продавца)"},
        {"code": "unknown", "label": "Не указано"},
    ],
    "technical_conditions": [
        {"code": "good", "label": "Исправен"},
        {"code": "needs_repair", "label": "Требует ремонта"},
        {"code": "non_operational", "label": "Не на ходу"},
    ],
    "body_conditions": [
        {"code": "good", "label": "Без заметных повреждений"},
        {"code": "minor_damage", "label": "Есть небольшие повреждения"},
        {"code": "significant_damage", "label": "Есть серьёзные повреждения"},
        {"code": "repaired", "label": "Был в ремонте"},
    ],
    "equipment": [
        {"code": "abs", "label": "ABS"},
        {"code": "esp", "label": "ESP"},
        {"code": "airbags", "label": "Подушки безопасности"},
        {"code": "air_conditioning", "label": "Кондиционер"},
        {"code": "climate_control", "label": "Климат-контроль"},
        {"code": "heated_seats", "label": "Подогрев сидений"},
        {"code": "cruise_control", "label": "Круиз-контроль"},
        {"code": "parking_sensors", "label": "Парктроники"},
        {"code": "rear_camera", "label": "Камера заднего вида"},
        {"code": "leather_seats", "label": "Кожаный салон"},
        {"code": "carplay", "label": "Apple CarPlay"},
        {"code": "android_auto", "label": "Android Auto"},
    ],
}
