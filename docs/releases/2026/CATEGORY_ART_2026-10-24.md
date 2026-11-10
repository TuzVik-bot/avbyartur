# Категорийные иллюстрации — 24.10.2026

Проверено: 34 подкатегорий, все файлы существуют и декодируются через `dwebp`. Прозрачные WebP оптимизированы из сгенерированных PNG с `cwebp -q 90 -alpha_q 100`. Арт в общем стиле: изолированные продуктовые рендеры, кобальтовый синий, тёмно-синий графит, оранжевые детали.

| Категория | Подкатегория | Путь |
|---|---|---|
| Мототехника | Мотоцикл | `web/public/category-art/motorcycles/motorcycle.webp` |
| Мототехника | Скутер | `web/public/category-art/motorcycles/scooter.webp` |
| Мототехника | Квадроцикл | `web/public/category-art/motorcycles/atv.webp` |
| Мототехника | Снегоход | `web/public/category-art/motorcycles/snowmobile.webp` |
| Спецтехника | Дорожно-строительная | `web/public/category-art/special-equipment/road-construction.webp` |
| Спецтехника | Коммунальная | `web/public/category-art/special-equipment/municipal.webp` |
| Спецтехника | Крановая | `web/public/category-art/special-equipment/crane.webp` |
| Спецтехника | Лесная | `web/public/category-art/special-equipment/forestry.webp` |
| Спецтехника | Погрузчик | `web/public/category-art/special-equipment/loader.webp` |
| Спецтехника | Подъёмная | `web/public/category-art/special-equipment/lift.webp` |
| Спецтехника | Бетонная | `web/public/category-art/special-equipment/concrete.webp` |
| Спецтехника | Эвакуатор | `web/public/category-art/special-equipment/tow-truck.webp` |
| Спецтехника | Экскаватор | `web/public/category-art/special-equipment/excavator.webp` |
| Спецтехника | Другая спецтехника | `web/public/category-art/special-equipment/other.webp` |
| Сельхозтехника | Животноводство | `web/public/category-art/agricultural-equipment/livestock.webp` |
| Сельхозтехника | Мини-техника | `web/public/category-art/agricultural-equipment/mini.webp` |
| Сельхозтехника | Подготовка почвы | `web/public/category-art/agricultural-equipment/soil-preparation.webp` |
| Сельхозтехника | Посевная | `web/public/category-art/agricultural-equipment/sowing.webp` |
| Сельхозтехника | Послеуборочная | `web/public/category-art/agricultural-equipment/post-harvest.webp` |
| Сельхозтехника | Прочая уборочная | `web/public/category-art/agricultural-equipment/other-harvest.webp` |
| Сельхозтехника | Зерноуборочная | `web/public/category-art/agricultural-equipment/grain-harvest.webp` |
| Сельхозтехника | Кормоуборочная | `web/public/category-art/agricultural-equipment/forage-harvest.webp` |
| Сельхозтехника | Овощная уборочная | `web/public/category-art/agricultural-equipment/vegetable-harvest.webp` |
| Сельхозтехника | Трактор | `web/public/category-art/agricultural-equipment/tractor.webp` |
| Сельхозтехника | Уход за посевами | `web/public/category-art/agricultural-equipment/crop-care.webp` |
| Сельхозтехника | Другая сельхозтехника | `web/public/category-art/agricultural-equipment/other.webp` |
| Водный транспорт | Гидроцикл | `web/public/category-art/watercraft/jetski.webp` |
| Водный транспорт | Лодка | `web/public/category-art/watercraft/boat.webp` |
| Водный транспорт | Мотор | `web/public/category-art/watercraft/outboard-motor.webp` |
| Водный транспорт | Другой водный транспорт | `web/public/category-art/watercraft/other-watercraft.webp` |
| Шины | Легковые | `web/public/category-art/tires/passenger-tire.webp` |
| Шины | Грузовые | `web/public/category-art/tires/truck-tire.webp` |
| Шины | Мотоциклетные | `web/public/category-art/tires/motorcycle-tire.webp` |
| Колёса | Колёсные диски | `web/public/category-art/wheels/alloy-wheel.webp` |

Последние три сельхоз-исходника перед конвертацией:

- `sowing.webp` ← `exec-1b45ae23-ed6a-4a56-aa47-0df0fcd277ea.png` (сеялка).
- `post-harvest.webp` ← `exec-bf36901d-6383-4711-bf7a-33fca3547ad0.png` (послеуборочный зерновой комплекс).
- `other-harvest.webp` ← `exec-d6e2025b-f9d3-4f08-a376-480d24f7cfaf.png` (трактор с косилкой).

Исходные PNG хранятся вне `public`; runtime использует WebP из перечисленных путей. Контактный лист показывает каждую иллюстрацию в слоте карточки 104×96 px.
