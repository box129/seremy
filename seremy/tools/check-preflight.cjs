// Browser checks for repository inspection before analysis; no model calls.
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
async function main(){
  const url=process.argv[2],archive=path.resolve(process.argv[3]),out=path.resolve(process.argv[4]);
  fs.mkdirSync(out,{recursive:true});
  const browser=await chromium.launch();const errors=[],checks=[];
  try{
    const page=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(url,{timeout:120000});await page.locator('#empty-connect').click();
    await page.locator('#limits-help').click();
    assert.match(await page.locator('#limits-section').innerText(),/180 seconds/);
    assert.match(await page.locator('#limits-section').innerText(),/HTML, CSS/);
    await page.screenshot({path:path.join(out,'mobile-limits-help.png')});await page.locator('#close-help').click();
    await page.locator('#zip').setInputFiles(archive);await page.locator('#start').click();
    await page.locator('#repository-check-title').waitFor({timeout:75000});
    assert.equal(await page.locator('#start').innerText(),'Analyze repository');
    assert.equal(await page.locator('#outputs').isVisible(),false);
    const checkText=await page.locator('#repository-check').innerText();
    assert.match(checkText,/23 supported source files/);assert.match(checkText,/compiled bundles/);
    assert.match(checkText,/static\/react\/app.js/);assert.match(checkText,/does not guarantee/);
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
    await page.locator('#repository-check').scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(out,'mobile-repository-check.png')});
    checks.push('Mobile limits help, repository measurements, bundle warning and explicit analysis confirmation');
    await page.reload();await page.locator('#empty-connect').click();
    await page.locator('#repository-check-title').waitFor({timeout:10000});
    assert.equal(await page.locator('#start').innerText(),'Analyze repository');
    checks.push('Reload restores a checked repository without starting analysis');
    await page.locator('#start').click();
    await page.waitForFunction(()=>!document.querySelector('#outputs').hidden||/time limit|could not finish/.test(document.querySelector('#connection-status').textContent),{},{timeout:200000});
    assert.equal(await page.locator('#outputs').isVisible(),true,await page.locator('#connection-status').innerText());
    await page.frameLocator('#map').locator('#status').filter({hasText:'source verified'}).waitFor({timeout:60000});
    const graph=await(await page.request.get(new URL(await page.locator('#download').getAttribute('href'),url).href)).json();
    assert.equal(graph.contents.coverage.s02.parsed_file_records,23);
    await page.screenshot({path:path.join(out,'mobile-sabi-map.png')});
    checks.push('Reported repository completes analysis and the browser verifies its source map');
    await page.setViewportSize({width:1440,height:900});
    await page.screenshot({path:path.join(out,'desktop-sabi-map.png')});
    await page.locator('#connect').click();await page.locator('#kind').selectOption('git');
    await page.locator('#value').fill('https://github.com/Mizzy006/Sabi');await page.locator('#revision').fill('3184572f7212cf3fa83101dabac7b3c3dd5be714');
    await page.locator('#start').click();await page.locator('#repository-check-title').waitFor({timeout:75000});
    await page.getByRole('button',{name:'frontend (',exact:false}).click();
    assert.equal(await page.locator('#source-folder').inputValue(),'frontend');
    assert.equal(await page.locator('#start').innerText(),'Check repository');
    assert.equal(await page.locator('#repository-check').isVisible(),false);
    checks.push('GitHub folder suggestions invalidate the old check and require a new one');
    assert.deepEqual(errors,[]);
    const result={status:'passed',checks,page_errors:errors,repository_check:checkText,coverage:graph.contents.coverage};
    fs.writeFileSync(path.join(out,'browser-checks.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({status:'passed',checks}));
  }finally{await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
