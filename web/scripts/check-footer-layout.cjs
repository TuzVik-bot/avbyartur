// Run against a local preview: node scripts/check-footer-layout.cjs [base-url].
const assert = require('node:assert/strict');
const { mkdirSync } = require('node:fs');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const output = '/private/tmp/avtorinok-footer';
  mkdirSync(output, { recursive: true });
  try {
    const page = await browser.newPage();
    const baseURL = process.argv[2] || 'http://127.0.0.1:3003';
    const response = await page.goto(`${baseURL}/about`, { waitUntil: 'networkidle' });
    assert.equal(response.status(), 200);
    const footer = page.locator('footer.site-footer');
    const linkCount = await footer.locator('a').count();
    for (const theme of ['light', 'dark']) {
      await page.evaluate(value => document.documentElement.dataset.theme = value, theme);
      for (const width of [1440, 1024, 768, 390, 320]) {
        await page.setViewportSize({ width, height: 1000 });
        await footer.scrollIntoViewIfNeeded();
        const height = (await footer.boundingBox()).height;
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `Overflow at ${width}px`);
        assert.equal(await footer.locator('a').count(), linkCount, 'Footer links lost');
        if (width >= 1024) assert.ok(height < 540, `Desktop footer too tall: ${height}px`);
        if (width <= 900) {
          assert.ok(height < 590, `Collapsed mobile footer too tall: ${height}px`);
          const toggle = footer.getByRole('button', { name: 'Объявления' });
          await toggle.click();
          await footer.getByRole('link', { name: 'Авто с пробегом', exact: true }).waitFor({ state: 'visible' });
          assert.equal(await toggle.getAttribute('aria-expanded'), 'true');
          await toggle.focus();
          await page.keyboard.press('Enter');
          assert.equal(await toggle.getAttribute('aria-expanded'), 'false');
          await footer.getByRole('link', { name: 'Авто с пробегом', exact: true }).waitFor({ state: 'hidden' });
        } else {
          assert.equal(await footer.locator('.footer-group-content:visible').count(), 5);
        }
        await page.locator('.footer-brand').focus();
        await footer.screenshot({ path: `${output}/${theme}-${width}.png` });
        console.log(`PASS ${theme} ${width}px: footer ${Math.round(height)}px, ${linkCount} links`);
      }
    }
    if (process.env.CHECK_RELEASE_UI === '1') {
      for (const choice of ['unknown', 'granted', 'denied']) {
        await page.evaluate(value => {
          if (value === 'unknown') localStorage.removeItem('avtorinok.contact_click_consent');
          else localStorage.setItem('avtorinok.contact_click_consent', value);
        }, choice);
        await page.reload({ waitUntil: 'networkidle' });
        assert.equal(await page.getByLabel('Настройки измерения обращений', { exact: true }).count(), 0);
        assert.equal(await page.getByText('Измерение обращений:', { exact: false }).count(), 0);
        assert.equal(await page.getByText('Измерять обращения к продавцам?', { exact: true }).count(), 0);
        assert.equal(await page.getByRole('button', { name: 'Открыть помощника Авторынка', exact: true }).isVisible(), true);
        assert.equal(await page.evaluate(() => localStorage.getItem('avtorinok.contact_click_consent')), choice === 'unknown' ? null : choice);
      }
      await page.setViewportSize({ width: 1440, height: 1000 });
      const login = await page.goto(`${baseURL}/login?next=%2Fsell`, { waitUntil: 'domcontentloaded' });
      assert.equal(login.status(), 200);
      await page.getByRole('button', { name: 'Создать аккаунт', exact: true }).click();
      for (const name of ['display_name', 'email', 'password', 'password_confirm', 'accept_terms', 'accept_privacy']) {
        await page.locator(`input[name="${name}"]`).waitFor({ state: 'visible' });
      }
      await page.getByRole('button', { name: 'Зарегистрироваться', exact: true }).waitFor({ state: 'visible' });
      console.log('PASS release UI: measurement block absent for all saved choices, assistant visible, registration form complete');
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
