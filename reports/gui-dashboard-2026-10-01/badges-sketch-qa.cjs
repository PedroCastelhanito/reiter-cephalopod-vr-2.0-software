const {chromium} = require('/Users/pedrocastelhanito/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict');
const base='/Users/pedrocastelhanito/.codex/visualizations/2026/10/01/01a0f6a6-67df-7941-875b-a12acf196161';
(async()=>{
 const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 const page=await browser.newPage({viewport:{width:1100,height:1100}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('file://'+base+'/dashboard-preview-sketches-check.html');
 const frame=page.frameLocator('iframe');
 await frame.locator('.cv-stage[data-design="compact"] .cv-shell').waitFor();
 for(const width of [1100,1024,736,390,320]){
  await page.setViewportSize({width,height:1100});
  for(const design of ['compact','previews','focused']){
   await frame.locator('#cephvr-sketches').evaluate((root,design)=>root.querySelectorAll('[data-variant]').forEach(v=>v.hidden=v.querySelector('.cv-stage').dataset.design!==design),design);
   await page.waitForTimeout(60);
   const stage=frame.locator(`.cv-stage[data-design="${design}"]`);
   const bounds=await stage.evaluate(el=>({client:el.clientWidth,scroll:el.scrollWidth,overflow:[...el.querySelectorAll('button,input,select,.cv-panel,.cv-console')].filter(x=>x.getBoundingClientRect().width&&x.getBoundingClientRect().right>el.getBoundingClientRect().right+1).map(x=>x.className)}));
   assert(bounds.scroll<=bounds.client+1,JSON.stringify({width,design,bounds}));
   assert.equal(bounds.overflow.length,0,JSON.stringify({width,design,bounds}));
   if(width===1100) await stage.screenshot({path:base+`/sketch-${design}.png`});
  }
  console.log(`Three layouts fit at ${width}px`);
 }
 await page.setViewportSize({width:1100,height:1100});
 for(const design of ['compact','previews','focused']){
  await frame.locator('#cephvr-sketches').evaluate((root,design)=>root.querySelectorAll('[data-variant]').forEach(v=>v.hidden=v.querySelector('.cv-stage').dataset.design!==design),design);
  const stage=frame.locator(`.cv-stage[data-design="${design}"]`);
  const preview=stage.locator('[data-viewer]').filter({visible:true}).first();
  await preview.click();assert.equal(await preview.textContent(),'Hide');
  await preview.click();assert.equal(await preview.textContent(),'Show');
  await stage.locator('[data-command="start"]').click();
  assert.equal(await stage.locator('[data-phase]').textContent(),'Running');
  await stage.locator('[data-command="stop"]').click();
  assert(await stage.locator('.cv-stop-dialog').isVisible());
  await stage.locator('[data-stop-choice="cancel"]').click();
  assert(!(await stage.locator('.cv-stop-dialog').isVisible()));
  if(design==='focused'){
   await stage.locator('.cv-log-tools select').selectOption('warnings');
   assert.equal(await stage.locator('.cv-log-text').textContent(),'No warnings or errors');
   await stage.locator('.cv-demographic-details summary').click();
   assert(await stage.locator('[aria-label="Subject age in dph"]').isVisible());
  }
 }
 assert.deepEqual(errors,[]);
 console.log('Preview toggles, local state, cancellation, log filter and subject disclosure passed; no page errors.');
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
