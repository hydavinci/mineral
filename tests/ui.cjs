const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
const base=process.env.TEST_URL || 'https://mineral.graymammoth.com/';
const out=process.env.ARTIFACT_DIR || '/tmp/mineral-tests';
require('node:fs').mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE,args:['--no-sandbox']});
 try {
  const context=await browser.newContext();
  await context.addInitScript(()=>sessionStorage.setItem('mineral_access','granted'));
  const page=await context.newPage(), errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base,{waitUntil:'domcontentloaded'});
  await page.waitForSelector('.card');
  await page.addStyleTag({content:'*, *::before, *::after { transition-duration: 0s !important; animation-duration: 0s !important; }'});
  for(const theme of ['light','dark']) {
   await page.emulateMedia({colorScheme:theme});
   for(const width of [1440,390,320]) {
    await page.setViewportSize({width,height:950});
    await page.locator('#addBtn').click();
    const styles=await page.evaluate(()=>{
     const css=s=>getComputedStyle(document.querySelector(s));
     return {dialog:css('.modal').backgroundColor,title:css('.modal h2').color,header:css('h1').color,input:css('#m-title').backgroundColor,text:css('#m-title').color,button:css('.btn-save').color,overflow:document.documentElement.scrollWidth>innerWidth};
    });
    assert.equal(styles.dialog,theme==='light'?'rgb(255, 255, 255)':'rgb(18, 18, 26)');
    assert.equal(styles.title,theme==='light'?'rgb(17, 17, 17)':'rgb(255, 255, 255)');
    assert.equal(styles.header,styles.title);
    assert.equal(styles.input,theme==='light'?'rgb(242, 242, 247)':'rgba(255, 255, 255, 0.04)');
    assert.equal(styles.button,theme==='light'?'rgb(255, 255, 255)':'rgb(8, 16, 24)');
    assert.equal(styles.overflow,false);
    await page.locator('#m-cat').focus();
    assert(await page.locator('#cat-list').isVisible());
    assert.equal(await page.locator('#cat-list').evaluate(n=>getComputedStyle(n).backgroundColor),theme==='light'?'rgb(255, 255, 255)':'rgb(26, 26, 42)');
    const popup=await page.locator('#cat-list').boundingBox(), dialog=await page.locator('.modal').boundingBox();
    assert(popup.y>=dialog.y && popup.y+popup.height<=dialog.y+dialog.height);
    await page.locator('#m-title').focus();
    await page.locator('#cat-list').waitFor({state:'hidden'});
    await page.screenshot({path:path.join(out,`modal-${theme}-${width}.png`)});
    await page.locator('#modalCancel').click();
   }
  }
  await page.emulateMedia({colorScheme:'light'});
  await page.setViewportSize({width:1440,height:950});
  // Actual public endpoint, no bookmark writes.
  await page.locator('#addBtn').click();
  await page.locator('#m-url').fill('example.com');
  await page.locator('#m-title').focus();
  await page.waitForFunction(()=>document.querySelector('#m-title').value==='Example Domain',null,{timeout:20000});
  assert.match(await page.locator('#m-fetching').textContent(),/已获取/);
  await page.locator('#m-url').fill('https://z-lib.by/');
  await page.locator('#m-title').focus();
  await page.waitForFunction(()=>document.querySelector('#m-fetching').textContent.includes('HTTP 503'),null,{timeout:20000});
  assert.equal(await page.locator('#m-title').inputValue(),'z-lib.by');
  await page.screenshot({path:path.join(out,'upstream-fallback.png')});
  await page.locator('#modalCancel').click();
  // Deterministic response/interaction tests; writes are intercepted, never persisted.
  let calls=0, pendingResolve, newResolve;
  let newStartedResolve;
  const newStarted=new Promise(resolve=>{newStartedResolve=resolve});
  let slowStartedResolve;
  const slowStarted=new Promise(resolve=>{slowStartedResolve=resolve});
  await page.route('**/api/fetch-meta',async route=>{
   calls++;
   const url=route.request().postDataJSON().url;
   if(url.includes('failure.example')) return route.fulfill({status:502,body:'Bad gateway'});
   if(url.includes('slow.example')) await new Promise(r=>{pendingResolve=r;slowStartedResolve()});
   if(url.includes('new.example')) await new Promise(r=>{newResolve=r;newStartedResolve()});
   await route.fulfill({json:{title:url.includes('slow.example')?'Old title':'New title',description:'Description',category:'Reading',status:'ok'}}).catch(()=>{});
  });
  await page.locator('#addBtn').click();
  await page.locator('#m-url').fill('https://slow.example');
  await page.locator('#m-title').focus();
  await page.waitForFunction(()=>document.querySelector('#m-fetching').textContent.includes('正在'));
  // Wait on observable request, not an arbitrary timing delay.
  await slowStarted;
  await page.locator('#m-url').fill('https://new.example');
  await page.locator('#m-title').fill('My manual title');
  await page.locator('#m-desc').focus();
  await newStarted;
  newResolve();
  pendingResolve();
  await page.waitForFunction(()=>document.querySelector('#m-fetching').textContent.includes('已获取'));
  assert.equal(await page.locator('#m-title').inputValue(),'My manual title');
  assert.equal(await page.locator('#m-desc').inputValue(),'Description');
  await page.locator('#modalCancel').click();
  await page.locator('#addBtn').click();
  await page.locator('#m-url').fill('https://failure.example');
  await page.locator('#m-title').focus();
  await page.waitForFunction(()=>document.querySelector('#m-fetching').textContent.includes('服务暂时不可用'));
  await page.locator('#modalCancel').click();
  let saved;
  await page.route('**/api/bookmarks', async route=>{
   assert.equal(route.request().method(),'POST');
   saved=route.request().postDataJSON();
   await route.fulfill({status:201,json:saved});
  });
  await page.locator('#addBtn').click();
  await page.locator('#m-url').fill('save.example');
  await page.locator('#modalSave').click();
  await page.waitForFunction(()=>!document.querySelector('#modal').classList.contains('active'));
  assert.equal(saved.title,'New title');
  assert.equal(saved.url,'https://save.example/');
  // Fetched text is rendered literally, never interpreted as HTML.
  await page.evaluate(()=>{bookmarks.push({title:'<img src=x onerror="window.injected=1">',url:'https://example.com',description:'A & B',category:'<b>Reading</b>',tags:[]});render();});
  assert.equal(await page.locator('.card-title img').count(),0);
  assert.equal(await page.evaluate(()=>window.injected),undefined);
  assert.deepEqual(errors,[]);
  console.log('PASS UI: light/dark x desktop/mobile, real title fetch and HTTP503 fallback, stale requests, manual edits, 502 hint, save waits for metadata, escaped text; no actual writes.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
