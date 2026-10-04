#!/usr/bin/env python3
"""Read-only browser smoke checks for the closed Avtorinok pilot UI."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from urllib.parse import quote_plus, urljoin, urlparse

from playwright.sync_api import Browser, BrowserContext, Page, Request, Response, TimeoutError as PlaywrightTimeoutError, sync_playwright


PUBLIC_ROUTES = {
    "/": "Ваш автомобиль уже ждёт вас",
    "/cars": "Автомобили Беларуси",
    "/dealers": "Компании и дилеры",
    "/help": "Помощь и правила пилота",
}
SELLER_ROUTES = {
    "/account": "Здравствуйте,",
    "/account/listings": "Мои объявления",
    "/account/favorites": "Избранное",
    "/account/company": "Компания",
    "/account/notifications": "Уведомления",
}
ADMIN_QUEUES = {
    "listings": "На проверке",
    "active": "Активные",
    "companies": "Компании",
    "reports": "Жалобы",
}


@dataclass
class Result:
    name: str
    passed: bool
    detail: str


class Smoke:
    def __init__(self, base_url: str, browser: Browser, basic_auth: tuple[str, str] | None):
        self.base_url = base_url.rstrip("/")
        self.origin = urlparse(self.base_url).netloc
        self.browser = browser
        self.basic_auth = basic_auth
        self.results: list[Result] = []
        self.page_errors: list[str] = []
        self.http_errors: list[str] = []

    def say(self, name: str, ok: bool, detail: str = "") -> None:
        self.results.append(Result(name, ok, detail))
        status = "PASS" if ok else "FAIL"
        suffix = f" - {detail}" if detail else ""
        print(f"[{status}] {name}{suffix}")

    def new_context(self, viewport: dict[str, int] | None = None) -> BrowserContext:
        context = self.browser.new_context(
            http_credentials=(
                {"username": self.basic_auth[0], "password": self.basic_auth[1]}
                if self.basic_auth
                else None
            ),
            viewport=viewport or {"width": 1440, "height": 1000},
            ignore_https_errors=False,
        )
        page = context.new_page()
        page.on("pageerror", lambda error: self.page_errors.append(str(error)))
        page.on("console", lambda message: self.page_errors.append(message.text) if message.type == "error" else None)
        page.on("requestfailed", self._on_request_failed)
        page.on("response", self._on_response)
        return context

    def _on_request_failed(self, request: Request) -> None:
        if self._same_origin(request.url):
            failure = request.failure or "request failed"
            if "ERR_ABORTED" not in failure:
                self.http_errors.append(f"{request.method} {self._safe_path(request.url)} failed ({failure})")

    def _on_response(self, response: Response) -> None:
        if self._same_origin(response.url) and response.status >= 500:
            self.http_errors.append(f"HTTP {response.status} {self._safe_path(response.url)}")

    def _same_origin(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.netloc == self.origin

    @staticmethod
    def _safe_path(url: str) -> str:
        parsed = urlparse(url)
        return parsed.path or "/"

    def visit(self, page: Page, path: str, expected_heading: str | None = None) -> bool:
        response = page.goto(urljoin(self.base_url + "/", path.lstrip("/")), wait_until="domcontentloaded")
        if response is None:
            self.say(f"GET {path}", False, "navigation returned no response")
            return False
        if response.status != 200:
            self.say(f"GET {path}", False, f"HTTP {response.status}")
            return False
        if expected_heading:
            heading = page.get_by_role("heading", name=expected_heading, exact=False).first
            try:
                heading.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeoutError:
                self.say(f"GET {path}", False, f"expected heading not visible after 10s: {expected_heading}")
                return False
        self.say(f"GET {path}", True, "HTTP 200")
        return True

    def public_routes(self, context: BrowserContext) -> tuple[Page, str | None]:
        page = context.pages[0]
        for path, heading in PUBLIC_ROUTES.items():
            self.visit(page, path, heading)

        # Run search through the visible home form and confirm the route renders.
        self.visit(page, "/cars", "Автомобили Беларуси")
        initial_listing_links = page.locator('a[aria-label^="Открыть объявление "]')
        search_term = None
        had_active_listing = initial_listing_links.count() > 0
        if initial_listing_links.count():
            first_title = page.locator("a.card-title").first.inner_text().strip()
            search_term = first_title.split()[0] if first_title else None

        if self.visit(page, "/", "Ваш автомобиль уже ждёт вас"):
            search = page.get_by_role("search")
            if search_term:
                search.locator('input[name="q"]').fill(search_term)
            search.get_by_role("button", name="Найти").click()
            page.wait_for_function(
                "() => window.location.pathname === '/cars'",
                timeout=15000,
            )
            self.say(
                "Home search navigation",
                urlparse(page.url).path == "/cars",
                self._safe_path(page.url),
            )
            if search_term:
                result_found = page.locator('a[aria-label^="Открыть объявление "]').count() > 0
                self.say("Search with matching result", result_found, "query from visible result")
            search_heading = page.get_by_role("heading", name="Автомобили Беларуси", exact=True)
            results_region = page.get_by_role("region", name="Результаты поиска")
            try:
                search_heading.wait_for(state="visible", timeout=10000)
                results_region.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeoutError:
                pass
            self.say(
                "Search page content",
                search_heading.count() == 1 and results_region.count() == 1,
            )

        # Search with a visible result when production data contains one; empty results are valid.
        search_path = f"/cars?q={quote_plus(search_term)}" if search_term else "/cars"
        self.visit(page, search_path, "Автомобили Беларуси")
        detail_path = None
        listing_links = page.locator('a[aria-label^="Открыть объявление "]')
        if had_active_listing and listing_links.count() == 0:
            self.visit(page, "/cars", "Автомобили Беларуси")
            listing_links = page.locator('a[aria-label^="Открыть объявление "]')
        if listing_links.count():
            href = listing_links.first.get_attribute("href")
            if href:
                detail_path = urlparse(urljoin(self.base_url, href)).path
                listing_links.first.click()
                try:
                    page.wait_for_url(f"**{detail_path}", timeout=10000)
                except Exception:
                    pass
                characteristics_heading = page.get_by_role("heading", name="Характеристики", exact=True)
                description_heading = page.get_by_role("heading", name="Описание", exact=True)
                try:
                    characteristics_heading.wait_for(state="visible", timeout=10000)
                    description_heading.wait_for(state="visible", timeout=10000)
                except PlaywrightTimeoutError:
                    pass
                detail_ok = (
                    urlparse(page.url).path == detail_path
                    and characteristics_heading.count() == 1
                    and description_heading.count() == 1
                )
                self.say("Listing detail navigation", detail_ok, self._safe_path(page.url))
            else:
                self.say("Listing detail navigation", False, "listing link has no href")
        elif not had_active_listing:
            self.say("Search result and detail", True, "no active listings; empty production catalog is allowed")
        else:
            self.say("Listing detail navigation", False, "active listing was present but could not be opened")

        # Guest favorite should send the browser to login with the selected detail as next.
        if detail_path and self.visit(page, detail_path):
            page.get_by_role("button", name="Добавить в избранное").click()
            page.wait_for_url("**/login?next=**")
            current = urlparse(page.url)
            query = current.query
            favorite_redirect_ok = current.path == "/login" and "next=" in query
            self.say("Guest favorite to login", favorite_redirect_ok)
        elif detail_path is None and not had_active_listing:
            self.say("Guest favorite to login", True, "skipped because production has no active listing")
        elif detail_path is None:
            self.say("Guest favorite to login", False, "active listing is present but its detail route was unavailable")

        return page, detail_path

    def mobile_overflow(self, context: BrowserContext, detail_path: str | None) -> None:
        page = context.new_page()
        page.on("pageerror", lambda error: self.page_errors.append(str(error)))
        page.on("console", lambda message: self.page_errors.append(message.text) if message.type == "error" else None)
        page.on("requestfailed", self._on_request_failed)
        page.on("response", self._on_response)
        page.set_viewport_size({"width": 390, "height": 844})
        paths = ["/", "/cars"] + ([detail_path] if detail_path else [])
        for path in paths:
            response = page.goto(urljoin(self.base_url + "/", path.lstrip("/")), wait_until="domcontentloaded")
            if response is None or response.status != 200:
                self.say(f"Mobile horizontal overflow {path}", False, f"HTTP {response.status if response else 'no response'}")
                continue
            dimensions = page.evaluate(
                """() => ({
                  viewport: document.documentElement.clientWidth,
                  document: document.documentElement.scrollWidth,
                  body: document.body.scrollWidth
                })"""
            )
            ok = dimensions["document"] <= dimensions["viewport"] + 1 and dimensions["body"] <= dimensions["viewport"] + 1
            self.say(f"Mobile horizontal overflow {path}", ok, str(dimensions))

    def login(self, page: Page, email: str, password: str, landing_path: str) -> bool:
        if not self.visit(page, "/login", "Вход в кабинет"):
            return False
        page.wait_for_load_state("networkidle")
        page.locator('input[name="email"]').fill(email)
        page.locator('input[name="password"]').fill(password)
        # The application's login endpoint is the only mutating request this runner performs.
        page.get_by_role("button", name="Войти").click()
        try:
            page.wait_for_url(f"**{landing_path}**", timeout=15000)
        except Exception:
            pass
        logged_in = urlparse(page.url).path == landing_path
        self.say("Application login", logged_in, self._safe_path(page.url))
        return logged_in

    def seller_routes(self, email: str, password: str) -> None:
        context = self.new_context()
        page = context.pages[0]
        if self.login(page, email, password, "/account"):
            for path, heading in SELLER_ROUTES.items():
                self.visit(page, path, heading)
        else:
            self.say("Seller account routes", False, "seller login did not reach /account")
        context.close()

    def admin_routes(self, email: str, password: str) -> None:
        context = self.new_context()
        page = context.pages[0]
        if self.login(page, email, password, "/account"):
            self.visit(page, "/moderation", "Модерация")
            queue_nav = page.get_by_role("navigation", name="Очередь модерации")
            for queue, label in ADMIN_QUEUES.items():
                link = queue_nav.get_by_role("link", name=label, exact=True)
                try:
                    link.wait_for(state="visible", timeout=10000)
                except PlaywrightTimeoutError:
                    self.say(f"Moderation queue tab: {label}", False, "tab not visible after 10s")
                    continue
                link.click()
                try:
                    page.wait_for_url(f"**queue={queue}**", timeout=10000)
                except Exception:
                    pass
                selected = page.locator('nav[aria-label="Очередь модерации"] a[aria-current="page"]')
                try:
                    page.wait_for_function(
                        "label => document.querySelector('nav[aria-label=\"Очередь модерации\"] a[aria-current=\"page\"]')?.textContent?.trim() === label",
                        arg=label,
                        timeout=10000,
                    )
                except PlaywrightTimeoutError:
                    pass
                correct = selected.count() == 1 and selected.inner_text().strip() == label
                self.say(f"Moderation queue tab: {label}", correct, self._safe_path(page.url))
        else:
            self.say("Moderation access", False, "admin login did not reach /account")
        context.close()


def env_pair(first: str, second: str) -> tuple[str, str] | None:
    values = (os.getenv(first, ""), os.getenv(second, ""))
    if any(values) and not all(values):
        raise ValueError(f"Set both {first} and {second}, or leave both unset")
    return (values[0], values[1]) if all(values) else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Pilot origin, for example http://127.0.0.1:3004")
    parser.add_argument("--headed", action="store_true", help="Run with a visible browser")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    basic_auth = env_pair("SMOKE_BASIC_AUTH_USER", "SMOKE_BASIC_AUTH_PASSWORD")
    seller = env_pair("SMOKE_SELLER_EMAIL", "SMOKE_SELLER_PASSWORD")
    admin = env_pair("SMOKE_ADMIN_EMAIL", "SMOKE_ADMIN_PASSWORD")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.headed)
        smoke = Smoke(args.base_url, browser, basic_auth)
        public_context = smoke.new_context()
        _, detail_path = smoke.public_routes(public_context)
        smoke.mobile_overflow(public_context, detail_path)
        public_context.close()

        if seller:
            smoke.seller_routes(*seller)
        else:
            print("[SKIP] Seller account routes - seller credentials are not configured")

        if admin:
            smoke.admin_routes(*admin)
        else:
            print("[SKIP] Moderation queues - admin credentials are not configured")

        browser.close()

    smoke.say("JavaScript errors", not smoke.page_errors, f"{len(smoke.page_errors)} error(s)" if smoke.page_errors else "none")
    smoke.say("Failed requests / server errors", not smoke.http_errors, f"{len(smoke.http_errors)} failure(s)" if smoke.http_errors else "none")
    for issue in smoke.page_errors[:5]:
        print(f"  JS: {issue[:240]}")
    for issue in smoke.http_errors[:8]:
        print(f"  Network: {issue[:240]}")
    failures = [result for result in smoke.results if not result.passed]
    print(f"\n{len(smoke.results) - len(failures)} passed, {len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as error:
        print(f"Smoke runner setup error: {error}", file=sys.stderr)
        raise SystemExit(2)
