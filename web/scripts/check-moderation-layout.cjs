// Run with node scripts/check-moderation-layout.cjs [path-to-css].
// Uses isolated markup matching the deployed moderation card; no account or DB.
const { readFileSync, mkdirSync } = require('node:fs');
const { resolve } = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');

(async () => {
  const css = readFileSync(resolve(process.argv[2] || 'src/app/globals.css'), 'utf8');
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    for (const width of [1440, 1024, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.setContent(`<style>${css}
        .photo-badge-editor { width:100%; margin-top:8px }
        .photo-badge-editor fieldset { min-width:0; margin:0; padding:12px; border:1px solid }
        .photo-badge-editor label { display:flex; gap:8px; min-height:36px }
        .photo-badge-editor input { width:17px; flex:none }
      </style><main style="padding:16px"><article class="account-list-item moderation-item">
        <div data-info><h2>Dacia Duster</h2><p>Nikita Karpuk · ревизия 19 · pending_review</p><details class="moderation-preview"><summary>Посмотреть сведения</summary><p>Описание автомобиля</p></details></div>
        <div class="moderation-actions"><button class="button">Одобрить</button>
        <details class="moderation-reason"><summary class="button">Отклонить</summary><label class="field">Причина<textarea></textarea></label></details>
        <button class="button">Заблокировать</button>
        <form class="photo-badge-editor"><fieldset><legend>Метки на фото</legend><p>Включайте метки после подтверждения проверки, бесплатной истории или лучшей цены. Изменения продавца сбросят метки.</p>
        ${['Проверено Авторынок', 'История бесплатно', 'Лучшая цена'].map(label => `<label><input type="checkbox">${label}</label>`).join('')}
        <button class="button">Сохранить метки</button></fieldset></form><button class="button">История правок</button></div>
      </article></main>`);
      for (const open of [false, true]) {
        await page.locator('.moderation-reason').evaluate((el, value) => { el.open = value; }, open);
        const bounds = await page.evaluate(() => {
          const rect = selector => { const r = document.querySelector(selector).getBoundingClientRect(); return { x:r.x, right:r.right, y:r.y, bottom:r.bottom }; };
          return { info:rect('[data-info]'), actions:rect('.moderation-actions'), editor:rect('.photo-badge-editor'), card:rect('article'), overflow:document.documentElement.scrollWidth > innerWidth };
        });
        try {
          assert.ok(bounds.actions.y >= bounds.info.bottom, `actions overlap information at ${width}px`);
          assert.ok(bounds.editor.x >= bounds.card.x && bounds.editor.right <= bounds.card.right, `editor outside card at ${width}px`);
          assert.equal(bounds.overflow, false, `horizontal overflow at ${width}px`);
        } catch (error) {
          mkdirSync('/private/tmp/avtorinok-moderation-layout', { recursive:true });
          await page.screenshot({ path:`/private/tmp/avtorinok-moderation-layout/failure-${width}.png`, fullPage:true });
          throw error;
        }
      }
    }
    console.log('PASS: moderation layout at 1440, 1024, 768, 390, 320px; rejection form closed/open');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
