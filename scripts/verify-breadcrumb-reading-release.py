#!/usr/bin/env python3
"""Read-only browser acceptance for breadcrumbs, reading time and registration."""
import argparse
import json
from pathlib import Path
from urllib.parse import quote
from playwright.sync_api import sync_playwright, expect


def verify(base_url, executable_path, artifacts):
    artifacts.mkdir(parents=True, exist_ok=True)
    checks = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=executable_path)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        try:
            response = page.goto(base_url + "/useful-information/articles")
            assert response and response.status == 200
            cards = page.locator('section[aria-label="Список статей"] article')
            assert cards.count() > 0
            for card in cards.all():
                expect(card).to_contain_text("мин чтения")
            article_href = cards.first.locator('h2 a').get_attribute("href")
            response = page.goto(base_url + article_href)
            assert response and response.status == 200
            expect(page.get_by_text("мин чтения", exact=False)).to_be_visible()
            checks.append("reading time visible in article cards and article")

            result = context.request.get(base_url + "/api/v1/listings", params={"q": "УАЗ", "page_size": "25"})
            assert result.status == 200
            listings = result.json()["items"]
            listing = next(item for item in listings if "Patriot" in item["title"] and item.get("make") and item.get("model"))
            make, model = listing["make"], listing["model"]
            href = "/cars/" + "/".join(quote(str(value), safe="") for value in [make["slug"], model["slug"], listing["id"]])
            response = page.goto(base_url + href)
            assert response and response.status == 200
            nav = page.get_by_role("navigation", name="Хлебные крошки")
            make_href = nav.get_by_role("link", name=make["name"], exact=True).get_attribute("href")
            model_href = nav.get_by_role("link", name=model["name"], exact=True).get_attribute("href")
            assert "manual-" not in make_href + model_href
            for target in [make_href, model_href]:
                response = page.goto(base_url + target)
                assert response and response.status == 200
                assert page.get_by_role("heading", name="404", exact=True).count() == 0
                assert listing["id"] in page.content(), "UAZ Patriot must remain in the filtered results"
            checks.append("real UAZ Patriot breadcrumbs open matching results with HTTP 200")

            response = page.goto(base_url + "/login?next=%2Fsell")
            assert response and response.status == 200
            page.get_by_role("button", name="Создать аккаунт", exact=True).click()
            for label in ["Имя", "Электронная почта", "Пароль", "Повторите пароль"]:
                expect(page.get_by_label(label, exact=True)).to_be_visible()
            expect(page.get_by_role("button", name="Зарегистрироваться", exact=True)).to_be_visible()
            assert page.get_by_role("checkbox").count() >= 2
            page.screenshot(path=str(artifacts / "registration.png"), full_page=True)
            checks.append("registration fields and consents available; no account submitted")
            print(json.dumps({"base_url": base_url, "passed": checks}, ensure_ascii=False, indent=2))
        except Exception:
            page.screenshot(path=str(artifacts / "failure.png"), full_page=True)
            (artifacts / "failure.html").write_text(page.content())
            raise
        finally:
            browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--browser-executable")
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    verify(args.base_url.rstrip("/"), args.browser_executable, args.artifacts)
