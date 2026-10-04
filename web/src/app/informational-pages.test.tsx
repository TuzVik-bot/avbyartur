import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
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
import { FAQ_TOPICS } from "@/components/faq-topics";

vi.mock("@/lib/legal-documents", () => ({ loadApprovedLegalDocument: vi.fn().mockResolvedValue(null) }));

describe("informational pilot pages", () => {
  const routes = [
    ["about", AboutPage, "Авторынок BY — закрытый пилот"],
    ["faq", FaqPage, "Частые вопросы"],
    ["support", SupportPage, "Поддержка закрытого пилота"],
    ["partner", PartnerPage, "Сотрудничество"],
    ["suggest-topic", SuggestTopicPage, "Предложить тему"],
    ["commenting-rules", CommentingRulesPage, "Правила комментариев"],
    ["material-using", MaterialUsingPage, "Использование материалов"],
    ["terms-of-use", TermsOfUsePage, "Условия использования"],
    ["privacy-policy", PrivacyPolicyPage, "Политика конфиденциальности"],
    ["cookie-policy", CookiePolicyPage, "Политика cookie"],
    ["submitting-advert", SubmittingAdvertPage, "Как подать объявление"],
    ["credit-policy", CreditPolicyPage, "Согласие на обработку персональных данных для фин. организаций"]
  ] as const;

  it.each(routes)("renders the %s route content", async (_route, Page, heading) => {
    const html = renderToStaticMarkup(await Page());
    expect(html).toContain(heading);
    expect(html).toContain("info-page");
  });

  it("describes guest-contact protections only for an explicitly enabled public mode", async () => {
    const html = renderToStaticMarkup(await CookiePolicyPage());
    expect(html).toContain("avtorinok_guest_contact_device");
    expect(html).toContain("avtorinok_guest_contact_proof");
    expect(html).toContain("24 часа");
    expect(html).toContain("15 минут");
    expect(html).toContain("В закрытом пилоте этот режим выключен");
  });

  it("keeps help and FAQ backed by the same pilot answers", () => {
    const helpHtml = renderToStaticMarkup(<HelpPage />);
    const faqHtml = renderToStaticMarkup(<FaqPage />);
    expect(FAQ_TOPICS.length).toBeGreaterThanOrEqual(6);
    for (const topic of FAQ_TOPICS) {
      expect(helpHtml).toContain(topic.title);
      expect(faqHtml).toContain(topic.title);
    }
  });

  it("labels legal pages as drafts without invented operator details", async () => {
    const legalHtml = [
      renderToStaticMarkup(await TermsOfUsePage()),
      renderToStaticMarkup(await PrivacyPolicyPage()),
      renderToStaticMarkup(await CookiePolicyPage()),
      renderToStaticMarkup(<MaterialUsingPage />)
    ].join(" ");
    expect(legalHtml).toContain("ПРОЕКТ / ЧЕРНОВИК");
    expect(legalHtml).not.toMatch(/admin@example|suite-s1\.denjik\.by|\+375\s*\d{9}/i);
  });

  it("makes clear the financial data consent is only a draft and is not collected", () => {
    const html = renderToStaticMarkup(<CreditPolicyPage />);
    expect(html).toContain("ПРОЕКТ / ЧЕРНОВИК");
    expect(html).toContain("передача данных финансовым организациям и сбор согласий не реализованы");
    expect(html).toContain("На этой странице нет формы или флажка для сбора согласия");
    expect(html).not.toMatch(/<input[^>]*type="checkbox"/i);
  });
});
