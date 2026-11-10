import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AboutPage from "@/app/about/page";
import CommentingRulesPage from "@/app/commenting-rules/page";
import CookiePolicyPage from "@/app/cookie-policy/page";
import CreditPolicyPage from "@/app/credit-policy/page";
import FaqPage from "@/app/faq/page";
import HelpPage from "@/app/help/page";
import MaterialUsingPage from "@/app/material-using/page";
import PartnerPage from "@/app/partner/page";
import PrivacyPolicyPage from "@/app/privacy-policy/page";
import SubmittingAdvertPage from "@/app/submitting-advert/page";
import SuggestTopicPage from "@/app/suggest-topic/page";
import SupportPage from "@/app/support/page";
import TermsOfUsePage from "@/app/terms-of-use/page";
import SaleContractPage from "@/app/sale-contract/page";
import { FAQ_TOPICS } from "@/components/faq-topics";
import { loadApprovedLegalDocument } from "@/lib/legal-documents";

vi.mock("@/lib/legal-documents", () => ({ loadApprovedLegalDocument: vi.fn() }));
beforeEach(() => vi.mocked(loadApprovedLegalDocument).mockReset().mockResolvedValue(null));

function parsed(html: string) { return new DOMParser().parseFromString(html, "text/html"); }

describe("public guides and documents", () => {
  const routes = [
    ["about", AboutPage, "Авторынок.бел"], ["faq", FaqPage, "Частые вопросы"],
    ["support", SupportPage, "Помощь при проблемах"], ["partner", PartnerPage, "Возможности для компаний"],
    ["suggest-topic", SuggestTopicPage, "Предложить тему"], ["commenting-rules", CommentingRulesPage, "Отзывы и общение"],
    ["material-using", MaterialUsingPage, "Использование материалов"], ["terms-of-use", TermsOfUsePage, "Условия использования"],
    ["privacy-policy", PrivacyPolicyPage, "Политика конфиденциальности"], ["cookie-policy", CookiePolicyPage, "Политика cookie"],
    ["submitting-advert", SubmittingAdvertPage, "Как подать объявление"],
    ["credit-policy", CreditPolicyPage, "Финансовые предложения и персональные данные"],
    ["sale-contract", SaleContractPage, "Договор купли-продажи автомобиля"]
  ] as const;

  it.each(routes)("renders %s with working contents anchors and no stale pilot claims", async (_route, Page, heading) => {
    const html = renderToStaticMarkup(await Page());
    const doc = parsed(html);
    expect(doc.querySelectorAll("h1")).toHaveLength(1);
    expect(doc.querySelector("h1")?.textContent).toBe(heading);
    expect(doc.querySelector(".info-page")).not.toBeNull();
    expect(doc.body.textContent).not.toMatch(/P0|Р0|публичной регистрации[^.]*нет|чата[^.]*нет|ОБРАЗЕЦ-001|ул\. Вымышленная/);
    for (const link of doc.querySelectorAll('nav[aria-label="На этой странице"] a')) {
      expect(doc.getElementById(link.getAttribute("href")!.slice(1)), link.textContent ?? "anchor").not.toBeNull();
    }
  });

  it("describes active technical protection, optional Google measurement and withdrawal honestly", async () => {
    const html = renderToStaticMarkup(await CookiePolicyPage());
    expect(html).toContain("avtorinok_guest_contact_device");
    expect(html).toContain("avtorinok_guest_contact_proof");
    expect(html).toContain("24 часа");
    expect(html).toContain("15 минут");
    expect(html).toContain("Google Analytics");
    expect(html).toContain("не удаляет ранее собранные данные");
    expect(html).not.toContain("В закрытом пилоте этот режим выключен");
    expect(html).not.toContain("аналитических или сторонних tracking-cookie");
  });

  it("keeps help and FAQ backed by the same current answers", () => {
    const helpHtml = renderToStaticMarkup(<HelpPage />);
    const faqHtml = renderToStaticMarkup(<FaqPage />);
    expect(FAQ_TOPICS.length).toBeGreaterThanOrEqual(6);
    for (const topic of FAQ_TOPICS) {
      expect(helpHtml).toContain(topic.title);
      expect(faqHtml).toContain(topic.title);
    }
  });

  it("does not present missing operator details or unapproved policies as final", async () => {
    for (const Page of [TermsOfUsePage, PrivacyPolicyPage, CookiePolicyPage]) {
      const html = renderToStaticMarkup(await Page());
      expect(html).toContain("Редакция для согласования");
      expect(html).not.toMatch(/admin@example|suite-s1\.denjik\.by|\+375\s*\d{9}|Утверждённый документ/);
    }
    const privacy = renderToStaticMarkup(await PrivacyPolicyPage());
    expect(privacy).toContain("OpenRouter");
    expect(privacy).toContain("не выполняет немедленное удаление");
    expect(privacy).toContain("ещё не предоставлены");
  });

  it("prefers the existing approved CMS document over the proposed replacement", async () => {
    vi.mocked(loadApprovedLegalDocument).mockResolvedValue({ title: "Действующий текст", body: "Утверждённое содержание <script>alert(1)</script>", version: "approved-version", operator: { legal_name: "Проверяемый оператор", unp: "123456789", address: "Указанный адрес", contact_email: "legal@invalid.test" } });
    const html = renderToStaticMarkup(await TermsOfUsePage());
    expect(html).toContain("Действующий текст");
    expect(html).toContain("approved-version");
    expect(html).toContain("&lt;script&gt;");
    expect(html).not.toContain("<script>");
    expect(html).not.toContain("Редакция для согласования");
  });

  it("does not collect an unavailable financial consent or show invented contract parties", () => {
    const html = renderToStaticMarkup(<CreditPolicyPage />);
    expect(html).toContain("согласия для такой передачи не собираются");
    expect(html).not.toMatch(/<input[^>]*type="checkbox"/i);
    const contract = renderToStaticMarkup(<SaleContractPage />);
    expect(contract).not.toMatch(/Иванов|Петрова|DEMO-VIN|25 000 BYN/);
    expect(contract).toContain("ГАИ");
  });
});
