const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

async function main() {
  const browser = await chromium.launch({ headless: true, ...(process.env.CHECK_BROWSER_CHANNEL ? { channel: process.env.CHECK_BROWSER_CHANNEL } : {}) });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const countRequests = [];
    page.on('request', request => {
      if (new URL(request.url()).pathname.endsWith('/listings/count')) countRequests.push(request.url());
    });
    await page.goto(`${process.env.CHECK_BASE_URL || 'https://xn--80aeylebmo7f.xn--90ais'}/cars`, { waitUntil: 'networkidle' });
    const input = page.getByRole('searchbox', { name: 'Поиск марки', exact: true });
    const select = page.getByLabel('Добавить марку', { exact: true });
    await input.click();
    const beforeTyping = countRequests.length;
    let value = '';
    for (const letter of 'Volvo') {
      value += letter;
      await input.pressSequentially(letter, { delay: 120 });
      const typed = await input.inputValue();
      if (typed !== value) {
        await page.screenshot({ path: process.env.CHECK_SCREENSHOT || '/tmp/av-catalog-input.png', fullPage: false });
        console.log(JSON.stringify({ expected: value, actual: typed, focus: await page.evaluate(() => document.activeElement?.outerHTML.slice(0, 500)), url: page.url() }));
      }
      assert.equal(await input.inputValue(), value, 'typing preserves every character');
      assert.equal(await input.evaluate(element => document.activeElement === element), true, 'typing preserves focus');
    }
    await page.waitForLoadState('networkidle');
    assert.equal(countRequests.length, beforeTyping, 'typing option text does not recount listings');
    console.log(JSON.stringify({ stage: 'typed', value: await input.inputValue(), options: await select.locator('option').allTextContents() }));
    await page.screenshot({ path: process.env.CHECK_SCREENSHOT || '/tmp/av-catalog-input.png', fullPage: false });
    await input.press('Enter');
    console.log(JSON.stringify({ stage: 'enter', selectedIds: await page.locator('input[name="make_ids"]').inputValue(), focusedElement: await page.evaluate(() => document.activeElement?.tagName), options: await select.locator('option').allTextContents() }));
    await select.selectOption({ label: 'Volvo' });
    assert.notEqual(await page.locator('input[name="make_ids"]').inputValue(), '', 'selecting a result adds the make');
    assert.equal(await input.inputValue(), '', 'selected make clears the search');
    const modelInput = page.getByRole('searchbox', { name: 'Поиск модели', exact: true });
    const modelSelect = page.getByLabel('Добавить модель', { exact: true });
    await page.waitForLoadState('networkidle');
    const firstModel = modelSelect.locator('option').nth(1);
    await firstModel.waitFor({ state: 'attached' });
    const expectedModelId = await firstModel.getAttribute('value');
    const query = (await firstModel.textContent()).replace(/^Volvo\s+/i, '').trim();
    await modelInput.click();
    let modelText = '';
    for (const letter of query) {
      modelText += letter;
      await modelInput.pressSequentially(letter, { delay: 120 });
      assert.equal(await modelInput.inputValue(), modelText, 'model typing preserves every character');
    }
    await page.waitForLoadState('networkidle');
    const option = modelSelect.locator(`option[value="${expectedModelId}"]`);
    await option.waitFor({ state: 'attached' });
    const modelId = await option.getAttribute('value');
    await modelSelect.selectOption(modelId);
    assert.equal(await page.locator('input[name="model_ids"]').inputValue(), modelId);
    assert.equal(await modelInput.inputValue(), '');
    console.log('PASS make/model typing, focus retention, option filtering and selection');
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error.message); process.exitCode = 1; });
