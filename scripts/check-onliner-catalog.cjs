const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.CHECK_BASE_URL || 'https://xn--80aeylebmo7f.xn--90ais';

async function main() {
  const browser = await chromium.launch({ headless: true, ...(process.env.CHECK_BROWSER_CHANNEL ? { channel: process.env.CHECK_BROWSER_CHANNEL } : {}) });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  try {
    await page.goto(base + '/cars', { waitUntil: 'networkidle' });
    const make = page.getByLabel('Добавить марку', { exact: true });
    await make.selectOption({ label: 'Jaguar' });
    const model = page.getByLabel('Добавить модель', { exact: true });
    await model.locator('option').filter({ hasText: 'XF' }).first().waitFor({ state: 'attached' });
    const options = await model.locator('option').allTextContents();
    for (const name of ['XE', 'XF', 'XJ', 'F-Pace', 'E-Pace', 'I-Pace']) {
      assert.ok(options.some(option => option.trim() === name || option.trim() === `Jaguar ${name}`), `Jaguar ${name} available`);
    }
    const xf = await model.locator('option').evaluateAll(options => options.find(option => /^(Jaguar )?XF$/.test(option.textContent.trim())).value);
    await model.selectOption(xf);
    assert.equal(await page.locator('input[name="model_ids"]').inputValue(), xf);
    const response = await page.request.get(base + '/api/v1/catalog/makes?q=' + encodeURIComponent('Ягуар'));
    assert.equal(response.status(), 200);
    assert.ok((await response.json()).items.some(item => item.slug === 'jaguar'));
    console.log('PASS production Jaguar selection, six principal model names, XF selection and Russian make search');
  } catch (error) {
    await page.screenshot({ path: process.env.CHECK_SCREENSHOT || '/tmp/onliner-catalog-check-failure.png' });
    throw error;
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error.message); process.exitCode = 1; });
