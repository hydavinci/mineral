const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE,args:['--no-sandbox']});
 const out=process.env.ARTIFACT_DIR || '/tmp/mineral-cards';fs.mkdirSync(out,{recursive:true});
 try {
  const context=await browser.newContext();
  await context.addInitScript(()=>sessionStorage.setItem('mineral_access','granted'));
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(process.env.TEST_URL || 'https://mineral.graymammoth.com/');
  await page.waitForSelector('.card-management');
  await page.addStyleTag({content:'* {animation:none !important;transition:none !important} .card {opacity:1}'});
  const overlaps=(a,b)=>a.x<b.x+b.width && b.x<a.x+a.width && a.y<b.y+b.height && b.y<a.y+a.height;
  for(const theme of ['light','dark']) {
   await page.emulateMedia({colorScheme:theme});
   for(const width of [1440,768,390,320]) {
    await page.setViewportSize({width,height:1000});
    const card=page.locator('.card').first();await card.hover();
    const category=await card.locator('.card-category').boundingBox();
    const actions=await card.locator('.card-actions').boundingBox();
    const link=await card.locator('.card-link').boundingBox();
    const title=await card.locator('.card-top').boundingBox();
    const header=await card.locator('.card-header').boundingBox();
    const titleText=await card.locator('.card-title').boundingBox();
    const description=await card.locator('.card-desc').boundingBox();
    const url=await card.locator('.card-url').boundingBox();
    assert(Math.abs(titleText.x-description.x)<1, 'title aligns with description');
    assert(Math.abs(titleText.x-url.x)<1, 'title aligns with URL');
    assert(!overlaps(category,actions));assert(!overlaps(link,actions));assert(!overlaps(title,actions));
    assert(Math.abs(actions.x+actions.width-header.x-header.width)<1);
    assert(Math.abs(actions.y-header.y)<1);
    assert.equal(await card.evaluate(n=>getComputedStyle(n).backgroundColor),theme==='light'?'rgb(255, 255, 255)':'rgb(17, 17, 25)');
    const btn=card.locator('.edit');await btn.hover();
    assert(!(await btn.evaluate(n=>getComputedStyle(n).backgroundColor)).startsWith('rgba'));
    assert((await btn.boundingBox()).width>=(width<=600?44:36));
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.screenshot({path:`${out}/cards-${theme}-${width}.png`});
   }
  }
  const first=page.locator('.card').first();
  await first.locator('.edit').click();
  await page.locator('#modal.active').waitFor();
  assert((await page.locator('#m-title').inputValue()).length>0);
  await page.locator('#modalCancel').click();
  const count=await page.locator('.card').count();
  page.once('dialog',dialog=>dialog.dismiss());
  await first.locator('.delete').click();
  assert.equal(await page.locator('.card').count(),count);
  // Long labels remain contained, not hidden beneath controls.
  await page.evaluate(()=>{bookmarks[0].category='Very long category '.repeat(10);bookmarks[0].title='Long title '.repeat(30);render();});
  const category=await first.locator('.card-category').boundingBox(), actions=await first.locator('.card-actions').boundingBox();
  assert(!overlaps(category,actions));
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await first.locator('.card-top').focus();
  await page.keyboard.press('Tab');
  assert.equal(await first.locator('.edit').evaluate(n=>getComputedStyle(n).outlineStyle),'solid');
  assert.deepEqual(errors,[]);
  console.log('PASS: left-aligned title/description/URL; opaque cards/actions; top-right actions without title/category/link overlap in 8 theme/viewport combinations; touch targets; long text; focus; edit/cancel-delete. No data writes.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
