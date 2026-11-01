const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.CHECK_BASE_URL || 'https://xn--80aeylebmo7f.xn--90ais';
async function main() {
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    const page = await context.newPage();
    await page.goto(base, { waitUntil: 'networkidle' });
    assert.equal(await page.title(), 'Автомобили Беларуси');
    for (const width of [320, 375, 390, 430]) {
      await page.setViewportSize({ width, height: 844 });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `overflow ${width}`);
      const account = page.locator('.header-actions a[aria-label="Кабинет"], .header-actions a[aria-label="Личный кабинет"]');
      assert.equal(await account.count(), 1);
      const box = await account.boundingBox();
      assert.ok(box && box.x >= 0 && box.x + box.width <= width, `account visible ${width}`);
      assert.match(await account.getAttribute('href'), /\/login\?next=%2Faccount$/);
    }
    console.log('PASS header widths 320/375/390/430 and cabinet link');
    await page.goto(base + '/login?next=%2Fsell', { waitUntil: 'networkidle' });
    await page.getByRole('button', { name: 'Создать аккаунт', exact: true }).click();
    for (const name of ['display_name', 'email', 'password', 'password_confirm', 'accept_terms', 'accept_privacy']) {
      await page.locator(`[name="${name}"]`).waitFor({ state: 'visible' });
    }
    await page.getByRole('button', { name: 'Зарегистрироваться', exact: true }).waitFor({ state: 'visible' });
    console.log('PASS production registration form');
    const response = await context.request.get(base + '/api/v1/listings?page_size=25');
    assert.equal(response.status(), 200);
    const data = await response.json();
    const listing = data.items.find(item => item.has_phone !== false && item.make);
    assert.ok(listing, 'real listing with phone');
    await page.goto(base + '/cars', { waitUntil: 'networkidle' });
    await page.locator('.filter-toggle').click();
    await page.locator('.filter-overlay[role="dialog"]').waitFor({ state: 'visible' });
    await page.getByLabel('Добавить марку', { exact: true }).selectOption(listing.make.id);
    await page.locator('.filter-apply').click();
    await page.waitForURL(url => url.searchParams.get('make_ids') === listing.make.id);
    await page.waitForLoadState('networkidle');
    const filteredResponse = await context.request.get(base + '/api/v1/listings?' + new URLSearchParams({ make_ids: listing.make.id, page_size: '25' }));
    assert.equal(filteredResponse.status(), 200);
    const filtered = await filteredResponse.json();
    assert.ok(filtered.pagination.total < data.pagination.total);
    assert.ok(filtered.items.every(item => item.make.id === listing.make.id));
    assert.equal(await page.locator('.filter-form input[name="make_ids"]').inputValue(), listing.make.id);
    assert.ok((await page.locator('.filter-result-count').innerText()).includes(String(filtered.pagination.total)));
    console.log('PASS mobile make filter and submitted results');
    await page.locator('.filter-toggle').click();
    const model = page.getByLabel('Добавить модель', { exact: true });
    await model.locator('option').nth(1).waitFor({ state: 'attached' });
    const modelId = await model.locator('option').nth(1).getAttribute('value');
    await model.selectOption(modelId);
    await page.locator('.filter-apply').click();
    await page.waitForURL(url => url.searchParams.get('model_ids') === modelId);
    await page.waitForLoadState('networkidle');
    const modelResponse = await context.request.get(base + '/api/v1/listings?' + new URLSearchParams({ make_ids: listing.make.id, model_ids: modelId, page_size: '25' }));
    assert.equal(modelResponse.status(), 200);
    const modelData = await modelResponse.json();
    assert.ok(modelData.items.every(item => item.make.id === listing.make.id && item.model.id === modelId));
    assert.equal(await page.locator('.filter-form input[name="model_ids"]').inputValue(), modelId);
    assert.ok((await page.locator('.filter-result-count').innerText()).includes(String(modelData.pagination.total)));
    console.log('PASS mobile make + model, including an empty matching result');
    const href = `/cars/${listing.make.slug}/${listing.model.slug}/${listing.id}`;
    await page.goto(base + href, { waitUntil: 'networkidle' });
    const revealResponse = page.waitForResponse(r => r.url().includes('/phone-reveal') && r.request().method() === 'POST');
    await page.locator('.contact-reveal').click();
    assert.equal((await revealResponse).status(), 200);
    await page.locator('.phone-revealed a[href^="tel:"]').waitFor({ state: 'visible' });
    assert.equal(await page.locator('.inline-error').count(), 0);
    assert.doesNotMatch(await page.locator('.detail-facts').innerText(), /navigation_system|seat_adjustment|wheel_configuration/);
    console.log('PASS real guest phone reveal and readable equipment (contact data omitted)');
    let exchange = data.items.find(item => item.exchange);
    for (let n = 2; !exchange && n <= 4; n++) {
      const r = await context.request.get(base + `/api/v1/listings?page_size=25&page=${n}`);
      assert.equal(r.status(), 200);
      exchange = (await r.json()).items.find(item => item.exchange);
    }
    if (!exchange) throw new Error('No real exchange listing available for browser verification');
    await page.goto(base + `/cars/${exchange.make.slug}/${exchange.model.slug}/${exchange.id}`, { waitUntil: 'networkidle' });
    const offer = page.getByRole('link', { name: 'Предложить обмен', exact: true });
    const target = new URL(await offer.getAttribute('href'), base);
    assert.equal(target.pathname, '/login');
    assert.ok(target.searchParams.get('next').includes('intent=exchange'));
    await offer.click();
    await page.waitForURL(url => url.pathname === '/login' && url.searchParams.get('next')?.includes('intent=exchange'));
    console.log('PASS exchange offer retains intent through guest login');
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
