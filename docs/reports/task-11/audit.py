import json
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:3003"
OUT = Path(__file__).parent / "after"
WIDTHS = (360, 390, 768, 1440)
PREFERENCES = ("system", "light", "dark")


def contrast_ratio(fg, bg):
    def channel(value):
        value = value / 255
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    def luminance(color):
        nums = [int(v) for v in re.findall(r"\d+", color)[:3]]
        if len(nums) != 3:
            return None
        return 0.2126 * channel(nums[0]) + 0.7152 * channel(nums[1]) + 0.0722 * channel(nums[2])

    a, b = luminance(fg), luminance(bg)
    if a is None or b is None:
        return None
    return round((max(a, b) + 0.05) / (min(a, b) + 0.05), 2)


rows = []
interaction = {}
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    browser_version = browser.version
    for width in WIDTHS:
        for preference in PREFERENCES:
            scheme = "dark" if preference == "dark" else "light"
            context = browser.new_context(
                viewport={"width": width, "height": 844 if width < 800 else 900},
                device_scale_factor=1,
                color_scheme=scheme,
                reduced_motion="no-preference",
            )
            if preference != "system":
                context.add_init_script(f'localStorage.setItem("avtorinok-theme", "{preference}")')
            page = context.new_page()
            response = page.goto(BASE + "/cars", wait_until="networkidle", timeout=90000)
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(300)
            scan = page.evaluate("""() => {
              const active = document.querySelector('[aria-label="Список"][aria-pressed="true"], [aria-label="Сетка"][aria-pressed="true"]');
              const rgb = (el, key) => el ? getComputedStyle(el)[key] : null;
              const controls = [...document.querySelectorAll('button, [role="button"]')].filter(el => {
                const r = el.getBoundingClientRect(); return r.width && r.height;
              });
              const noName = controls.filter(el => !(el.getAttribute('aria-label') || el.getAttribute('title') || el.innerText || '').trim())
                .map(el => ({tag: el.tagName, className: String(el.className).slice(0, 80)}));
              const short = controls.filter(el => {
                const r = el.getBoundingClientRect(); return r.width < 44 || r.height < 44;
              }).map(el => ({name: (el.getAttribute('aria-label') || el.innerText || '').trim().slice(0, 60), width: Math.round(el.getBoundingClientRect().width), height: Math.round(el.getBoundingClientRect().height)}));
              return {
                viewport: {width: innerWidth, height: innerHeight}, scrollWidth: document.documentElement.scrollWidth,
                clientWidth: document.documentElement.clientWidth,
                overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                theme: document.documentElement.dataset.theme,
                reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches,
                activeText: active?.innerText.trim() ?? null,
                activeContrast: active ? {foreground: rgb(active, 'color'), background: rgb(active, 'backgroundColor')} : null,
                shortControls: short, unnamedControls: noName,
                cards: document.querySelectorAll('.listing-card').length
              };
            }""")
            if scan["activeContrast"]:
                scan["contrastRatio"] = contrast_ratio(scan["activeContrast"]["foreground"], scan["activeContrast"]["background"])
            rows.append({"width": width, "preference": preference, "system_scheme": scheme, "status": response.status if response else None, "scan": scan})
            page.screenshot(path=str(OUT / f"a11y-{width}-{preference}.png"), full_page=True, animations="disabled")
            context.close()

    context = browser.new_context(viewport={"width": 720, "height": 900}, device_scale_factor=1)
    page = context.new_page()
    page.goto(BASE + "/cars", wait_until="networkidle", timeout=90000)
    page.evaluate("document.fonts.ready")
    zoom = page.evaluate("""() => ({viewportWidth: innerWidth, scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth, overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth})""")
    interaction["zoom_200_effective_720px"] = zoom

    # Exercise the actual list/grid controls and confirm the state change.
    page.get_by_role("button", name="Список").click()
    list_selected = page.get_by_role("button", name="Список").get_attribute("aria-pressed") == "true"
    page.get_by_role("button", name="Сетка").click()
    grid_selected = page.get_by_role("button", name="Сетка").get_attribute("aria-pressed") == "true"
    interaction["display_switch"] = {"list_selected": list_selected, "grid_selected": grid_selected}

    # Open the filter drawer, dismiss with Escape, and verify focus returns to its trigger.
    filter_trigger = page.get_by_role("button", name=re.compile("Фильтры"))
    filter_trigger.click()
    drawer_open = page.locator(".search-filters.is-open").count() == 1
    page.keyboard.press("Escape")
    focus_returned = page.evaluate("document.activeElement?.textContent?.includes('Фильтры') ?? false")
    interaction["filter_drawer"] = {"opened": drawer_open, "closed_with_escape": not page.locator(".search-filters.is-open").count(), "focus_returned": focus_returned}

    context.close()

    menu_context = browser.new_context(viewport={"width": 390, "height": 844})
    menu_page = menu_context.new_page()
    menu_page.goto(BASE + "/cars", wait_until="networkidle", timeout=90000)
    menu = menu_page.get_by_role("button", name="Открыть меню")
    menu.click()
    menu_open = menu_page.locator("#main-navigation.is-open").count() == 1
    menu_page.keyboard.press("Escape")
    interaction["header_menu"] = {
        "opened": menu_open,
        "closed_with_escape": menu_page.locator("#main-navigation.is-open").count() == 0,
        "focus_returned": menu_page.evaluate("(el) => document.activeElement === el", menu.element_handle()),
    }
    menu_context.close()

    reduced = browser.new_context(viewport={"width": 390, "height": 844}, reduced_motion="reduce")
    reduced_page = reduced.new_page()
    reduced_page.goto(BASE + "/cars", wait_until="networkidle", timeout=90000)
    reduced_page.evaluate("document.fonts.ready")
    interaction["reduced_motion"] = reduced_page.evaluate("""() => ({requested: matchMedia('(prefers-reduced-motion: reduce)').matches, overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth})""")
    reduced.close()
    browser.close()

result = {
    "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "browser": "Chromium",
    "browser_version": browser_version,
    "route": "/cars",
    "viewport_widths": list(WIDTHS),
    "preferences": list(PREFERENCES),
    "zoom_method": "720 CSS px effective viewport as a 1440 px viewport at 200% zoom; no browser UI zoom control used",
    "rows": rows,
    "interactions": interaction,
}
(OUT / "accessibility.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps({"rows": len(rows), "overflow": sum(r["scan"]["overflow"] for r in rows), "min_active_contrast": min((r["scan"]["contrastRatio"] for r in rows if r["scan"].get("contrastRatio") is not None), default=None), "interactions": interaction}, ensure_ascii=False, indent=2))
