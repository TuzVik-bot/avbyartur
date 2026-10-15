import json, statistics, time, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
BASE='http://localhost:3003'; PHASE=sys.argv[1] if len(sys.argv)>1 else 'before'
OUT=Path('/Users/home/.codex/worktrees/catalog-product-luna/avbyartur/docs/reports/task-11')/PHASE
ROUTES={'home':'/','catalog':'/cars','detail':'/cars/bmw/3-series/00000000-0000-4000-8000-000000000001'}
VIEWPORTS={'mobile':{'width':390,'height':844},'desktop':{'width':1440,'height':900}}
rows=[]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True); version=browser.version
 for device,vp in VIEWPORTS.items():
  for route_name,route in ROUTES.items():
   for cache in ('cold','warm'):
    warm_context=browser.new_context(viewport=vp,device_scale_factor=1,color_scheme='light',reduced_motion='no-preference') if cache=='warm' else None
    for run in range(1,4):
     context=warm_context if cache=='warm' else browser.new_context(viewport=vp,device_scale_factor=1,color_scheme='light',reduced_motion='no-preference'); page=context.new_page()
     page.add_init_script("window.__task11Perf={lcp:0,cls:0};try{new PerformanceObserver(l=>{for(const e of l.getEntries())window.__task11Perf.lcp=e.startTime}).observe({type:'largest-contentful-paint',buffered:true});new PerformanceObserver(l=>{for(const e of l.getEntries())if(!e.hadRecentInput)window.__task11Perf.cls+=e.value}).observe({type:'layout-shift',buffered:true})}catch(e){}")
     if cache=='warm' and run==1:
      page.goto(BASE+route,wait_until='networkidle',timeout=90000);page.evaluate('document.fonts.ready');page.wait_for_timeout(500)
     started=time.perf_counter();response=page.goto(BASE+route,wait_until='networkidle',timeout=90000);page.evaluate('document.fonts.ready');page.wait_for_timeout(500)
     nav=page.evaluate("() => {const n=performance.getEntriesByType('navigation')[0];return {responseStart:n?.responseStart??null,domContentLoaded:n?.domContentLoadedEventEnd??null,load:n?.loadEventEnd??null,lcp:window.__task11Perf?.lcp??null,cls:window.__task11Perf?.cls??null,scrollWidth:document.documentElement.scrollWidth,clientWidth:document.documentElement.clientWidth,title:document.title}}")
     row={'device':device,'viewport':vp,'device_scale_factor':1,'route_name':route_name,'route':route,'cache':cache,'run':run,'status':response.status if response else None,'elapsed_ms':round((time.perf_counter()-started)*1000,1),**nav};rows.append(row)
     if run==1:page.screenshot(path=str(OUT/f'{device}-{route_name}-{cache}.png'),full_page=True,animations='disabled')
     if cache=='cold':context.close()
     else:page.close()
     print(json.dumps(row,ensure_ascii=False),flush=True)
    if warm_context:warm_context.close()
 browser.close()
meta={'browser':'Chromium','browser_version':version,'viewport_matrix':VIEWPORTS,'device_scale_factor':1,'cache':'cold=fresh browser context per measured run; warm=one route warm-up then 3 navigations in same context','wait':'goto networkidle + document.fonts.ready + 500ms settle','api':'local Python synthetic mock at 127.0.0.1:8003; deterministic listing, test-only auth/contact responses; no database','network':'unthrottled local loopback','runs_per_cell':3,'generated_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
medians={}
for d in VIEWPORTS:
 for rn in ROUTES:
  for c in ('cold','warm'):
   xs=[r for r in rows if r['device']==d and r['route_name']==rn and r['cache']==c];medians[f'{d}/{rn}/{c}']={k:statistics.median([x[k] for x in xs if x[k] is not None]) for k in ('elapsed_ms','responseStart','domContentLoaded','load','lcp','cls')}
(OUT/'measurements.json').write_text(json.dumps({'config':meta,'rows':rows,'medians':medians},ensure_ascii=False,indent=2));print(json.dumps({'browser_version':version,'medians':medians},ensure_ascii=False,indent=2))
