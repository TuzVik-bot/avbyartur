import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:3003"
OUT = Path(__file__).parent / "after"
result = {"generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "scenarios": {}}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 390, "height": 844}, color_scheme="light")

    page = context.new_page()
    response = page.goto(BASE + "/login?next=%2Fsell", wait_until="networkidle", timeout=90000)
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(250)
    result["scenarios"]["registration"] = page.evaluate("""() => ({
      status: document.querySelector('main') ? 'main-rendered' : 'missing-main',
      url: location.pathname + location.search,
      title: document.title,
      text: document.querySelector('main')?.innerText.slice(0, 1500) ?? '',
      inputs: [...document.querySelectorAll('main input')].map(x => ({type: x.type, name: x.name, label: x.labels?.[0]?.innerText ?? x.getAttribute('aria-label')})),
      buttons: [...document.querySelectorAll('main button')].map(x => ({text: x.innerText.trim(), disabled: x.disabled}))
    })""")
    result["scenarios"]["registration"]["http_status"] = response.status if response else None
    capability = page.request.get(BASE + "/api/v1/auth/capabilities")
    result["scenarios"]["registration"]["capability_http_status"] = capability.status
    page.get_by_role("button", name="Создать аккаунт").click()
    result["scenarios"]["registration"]["create_account"] = page.evaluate("""() => ({
      inputNames: [...document.querySelectorAll('main input')].map(x => x.name),
      consentCheckboxes: [...document.querySelectorAll('main input[type=checkbox]')].map(x => ({name: x.name, required: x.required})),
      submitText: document.querySelector('main button[type=submit]')?.innerText.trim(),
      pilotNoticeVisible: document.querySelector('main')?.innerText.includes('тестовом режиме') ?? false
    })""")
    page.screenshot(path=str(OUT / "scenario-login-registration.png"), full_page=True, animations="disabled")
    page.screenshot(path=str(OUT / "scenario-login.png"), full_page=True, animations="disabled")

    response = page.goto(BASE + "/sell", wait_until="networkidle", timeout=90000)
    page.evaluate("document.fonts.ready")
    result["scenarios"]["sell"] = {"http_status": response.status if response else None, "final_url": page.url, "title": page.title()}
    page.screenshot(path=str(OUT / "scenario-sell-guest.png"), full_page=True, animations="disabled")

    page.goto(BASE + "/cars", wait_until="networkidle", timeout=90000)
    page.evaluate("document.fonts.ready")
    compare = page.get_by_role("button", name="Сравнить").first
    before_text = compare.inner_text()
    compare.click()
    page.wait_for_timeout(200)
    after_text = page.get_by_role("button", name="В сравнении").first.inner_text()
    storage = page.evaluate("localStorage.getItem('avtorinok.compare.v1')")
    links = page.locator('a[href="/compare"]').evaluate_all("xs => xs.map(x => ({text: x.innerText.trim(), aria: x.getAttribute('aria-label')}))")
    result["scenarios"]["compare"] = {"before": before_text, "after": after_text, "stored_state": storage, "compare_link_visible": bool(links), "compare_links": links}
    page.screenshot(path=str(OUT / "scenario-compare.png"), full_page=True, animations="disabled")

    detail = browser.new_page(viewport={"width": 390, "height": 844})
    response = detail.goto(BASE + "/cars/bmw/3-series/00000000-0000-4000-8000-000000000001", wait_until="networkidle", timeout=90000)
    detail.evaluate("document.fonts.ready")
    result["scenarios"]["contact"] = detail.evaluate("""() => {
      const button = [...document.querySelectorAll('button')].find(x => x.innerText.includes('Показать телефон'));
      return {url: location.pathname, hasContactActions: !!document.querySelector('button.contact-reveal, a[href^="tel:"], a[href*="t.me/"], a[href*="viber.me/"]'), phoneButtonVisible: !!button, phoneButtonDisabled: button?.disabled ?? null, contactText: document.querySelector('main')?.innerText.slice(-800) ?? ''};
    }""")
    result["scenarios"]["contact"]["http_status"] = response.status if response else None
    phone_responses = []
    detail.on("response", lambda r: phone_responses.append({"url_path": r.url.split("?")[0].replace(BASE, ""), "status": r.status}) if "contact" in r.url or "phone" in r.url else None)
    detail.get_by_role("button", name="Показать телефон").click()
    detail.wait_for_timeout(300)
    result["scenarios"]["contact"]["reveal_result"] = detail.evaluate("""() => ({revealed: document.querySelectorAll('a[href^="tel:"]').length > 0, visiblePhoneButton: [...document.querySelectorAll('button')].some(x => x.innerText.includes('Показать телефон')), messengerButtons: [...document.querySelectorAll('a')].filter(x => ['Telegram', 'Viber'].includes(x.innerText.trim())).map(x => x.innerText.trim()), error: !!document.querySelector('[role="alert"]')})""")
    result["scenarios"]["contact"]["request_statuses"] = phone_responses
    detail.screenshot(path=str(OUT / "scenario-detail-contact.png"), full_page=True, animations="disabled")

    context.close()
    browser.close()

(OUT / "scenarios.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps(result, ensure_ascii=False, indent=2))
