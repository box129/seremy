const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');

async function run(){
  const url=process.argv[2],evidence=path.resolve(process.argv[3]);
  fs.mkdirSync(evidence,{recursive:true});
  const browser=await chromium.launch(process.env.CHROME_BIN?{executablePath:process.env.CHROME_BIN}:{});
  const errors=[];
  try{
    const page=await browser.newPage({viewport:{width:1440,height:900}});
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(url,{timeout:120000});
    await page.locator('#empty-connect').click();
    await page.locator('#kind').selectOption('git');
    await page.locator('#value').fill('https://github.com/pallets/itsdangerous');
    await page.locator('#start').click();
    await page.waitForFunction(()=>document.querySelector('#outputs').hidden===false||document.querySelector('#status').textContent.startsWith('Analysis failed'),{},{timeout:210000});
    assert.equal(await page.locator('#outputs').isVisible(),true,await page.locator('#status').innerText());
    await page.frameLocator('#map').locator('#status').filter({hasText:'source verified'}).waitFor();
    const response=await page.request.get(new URL(await page.locator('#download').getAttribute('href'),url).href);
    assert.equal(response.status(),200);
    const graph=await response.json();
    const snapshot=graph.contents.snapshot;
    assert.equal(snapshot.repository_id,'git:https://github.com/pallets/itsdangerous');
    assert.match(JSON.stringify(snapshot),/git:https:\/\/github.com\/pallets\/itsdangerous@[0-9a-f]{40}/);
    assert.ok(graph.contents.coverage.s02.parsed_file_records>0);
    assert.deepEqual(errors,[]);
    const result={status:'passed',url,checks:['Public GitHub URL imports without repository execution','Graph identifies GitHub repository and resolved 40-character commit','Source map verifies downloaded source'],page_errors:errors};
    fs.writeFileSync(path.join(evidence,'checks.json'),JSON.stringify(result,null,2)+'\n');
    console.log(JSON.stringify(result));
  }finally{await browser.close();}
}
run().catch(error=>{console.error(error);process.exitCode=1;});
