// Optional UI QA. Requires Playwright and an installed Edge browser.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const path=require('node:path'),fs=require('node:fs'),assert=require('node:assert');
const {pathToFileURL}=require('node:url');
(async()=>{
 const root=path.resolve(__dirname,'../..');
 const browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL || 'msedge',headless:true});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(pathToFileURL(path.join(root,'demo/index.html')).href);
  assert((await page.locator('#hypothesis').innerText()).includes('может снизить расходы порта Ванино'));
  for(const key of ['base','positive','stress','failure']){
   await page.locator(`[data-preset="${key}"]`).click();
   assert.equal(await page.locator('#partyRows tr').count(),6);
   assert(!(await page.locator('#gateTerminal').isChecked()));
  }
  await page.locator('[data-preset="stress"]').click();
  await page.locator('[name="pool"]').selectOption('0');
  assert(Math.abs(await page.evaluate(()=>last.final[0])+70196.6)<.001);
  await page.locator('[name="n"]').fill('');assert(await page.locator('#error').isVisible());
  await page.locator('[data-preset="base"]').click();
  await page.locator('[data-route="vanino"]').click();await page.locator('#play').click();
  await page.waitForTimeout(350);assert(await page.evaluate(()=>progress>0));await page.locator('#play').click();
  const [download]=await Promise.all([page.waitForEvent('download'),page.locator('#download').click()]);
  assert.equal(download.suggestedFilename(),'A3_RZD_calculation.json');
  await page.setViewportSize({width:390,height:844});await page.evaluate(()=>scrollTo(0,0));
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  fs.mkdirSync(path.join(root,'local/browser'),{recursive:true});
  await page.screenshot({path:path.join(root,'local/browser/mobile.png')});
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(root,'model/results/browser_checks.json'),JSON.stringify({browser:'Edge headless',viewports:['1440x1000','390x844'],pageErrors:errors,scenarios:4,settlementModes:2,invalidInput:true,mapAnimation:true,export:true,exactHypothesis:true,mobileNoOverflow:true},null,2)+'\n');
  console.log('Browser checks passed');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
