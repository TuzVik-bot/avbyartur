const assert = require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.env.CHECK_BASE_URL||'https://xn--80aeylebmo7f.xn--90ais';
async function main(){
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{
 const page=await browser.newPage();
 await page.goto(base,{waitUntil:'networkidle'});
 assert.equal(await page.title(),'Автомобили Беларуси');
 assert.equal(await page.locator('body title, body meta[name="robots"], body link[rel="canonical"]').count(),0);
 assert.equal(await page.locator('head script[src*="gtag/js?id=G-48P5WKB0Z5"]').count(),1);
 const canonical=await page.locator('head link[rel="canonical"]').getAttribute('href');
 const sitemapResponse=await page.request.get(base+'/sitemap.xml');assert.equal(sitemapResponse.status(),200);
 const xml=await sitemapResponse.text();assert.ok(xml.includes('<loc>'+canonical+'</loc>'),'root canonical matches sitemap');
 const urls=[...xml.matchAll(/<loc>(.*?)<\/loc>/g)].map(x=>x[1]);
 assert.ok(!urls.some(u=>/\/cars\/manual-[^/]+$|\/cars\/[^/]+\/manual-[^/]+$/.test(u)),'no fallback landings');
 assert.ok(urls.some(u=>/\/manual-[^/]+\/[^/]+$/.test(u)),'real fallback listings retained');
 assert.ok(xml.includes('<lastmod>')&&xml.includes('<changefreq>monthly</changefreq>'));
 for(const path of ['/buses','/trucks','/parts','/trailers','/google92cb22c344dbd143.html','/yandex_8cebfb4be81fa555.html'])assert.equal((await page.request.get(base+path)).status(),200,path);
 console.log('PASS head metadata, GA, sitemap and footer routes; sitemap URLs='+urls.length);
 await page.goto(base+'/cars?condition=used&page=2',{waitUntil:'networkidle'});
 assert.match(await page.locator('head meta[name="robots"]').getAttribute('content'),/noindex.*follow/);
 const select=page.getByRole('combobox',{name:'Сортировка'});
 const modes=['newest','price_asc','price_desc','published_desc','oldest','mileage_asc','year_desc','year_asc'];
 assert.deepEqual(await select.locator('option').evaluateAll(xs=>xs.map(x=>x.value)),modes);
 await select.selectOption('year_asc');await page.waitForURL(u=>u.searchParams.get('sort')==='year_asc');
 assert.equal(new URL(page.url()).searchParams.get('condition'),'used');assert.ok(!new URL(page.url()).searchParams.has('page'));
 for(const sort of modes){const r=await page.request.get(base+'/api/v1/listings?'+new URLSearchParams({sort,page_size:'25',currency:'BYN'}));assert.equal(r.status(),200,sort);const d=await r.json();const field=sort.startsWith('year_')?'year':sort==='mileage_asc'?'mileage_km':null;if(field){let prev=null,missing=false;for(const x of d.items){const v=x[field];if(v==null){missing=true;continue;}assert.ok(!missing,sort+' nulls last');if(prev!=null)assert.ok(sort==='year_desc'?prev>=v:prev<=v,sort+' order');prev=v;}}}
 console.log('PASS eight sorts, API order, query robots, retained filter and page reset');
 await page.goto(base+'/login?next=%2Fsell',{waitUntil:'networkidle'});await page.getByRole('button',{name:'Создать аккаунт',exact:true}).click();
 for(const name of ['display_name','email','password','password_confirm','accept_terms','accept_privacy'])await page.locator(`[name="${name}"]`).waitFor({state:'visible'});
 await page.getByRole('button',{name:'Зарегистрироваться',exact:true}).waitFor({state:'visible'});
 console.log('PASS live registration form');
 await page.goto(base+'/cars',{waitUntil:'networkidle'});
 const images=page.locator('img[alt^="Продажа авто —"]');assert.ok(await images.count()>0,'automatic photo alt');
 console.log('PASS automatic image alt');
 const models=urls.filter(u=>new URL(u).pathname.split('/').filter(Boolean).length===3&&new URL(u).pathname.startsWith('/cars/')&&!u.includes('/city/'));
 if(models.length){await page.goto(models.find(u=>u.includes('/toyota/'))||models[0],{waitUntil:'networkidle'});const h1=(await page.locator('h1').innerText()).trim();assert.match(h1,/^Продажа /);assert.match(await page.title(),/^Купить /);assert.equal(await page.locator('body title,body meta[name="robots"],body link[rel="canonical"]').count(),0);console.log('PASS model H1/Title and metadata placement');}

 }finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
