// Exercise the deployed upload flow through the browser, including refresh recovery.
const {chromium}=require('playwright');
const {execFileSync}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');

async function run(){
  const url=process.argv[2],evidence=path.resolve(process.argv[3]);
  fs.mkdirSync(evidence,{recursive:true});
  const fixture=path.resolve(__dirname,'../fixtures/local-demo');
  const archive=execFileSync(process.env.PYTHON||'python',['-B','-c',
    'import io,pathlib,sys,zipfile\nb=io.BytesIO()\nroot=pathlib.Path(sys.argv[1])\nwith zipfile.ZipFile(b,"w") as z:\n for f in root.rglob("*"):\n  if f.is_file(): z.write(f,"repo/"+f.relative_to(root).as_posix())\nsys.stdout.buffer.write(b.getvalue())',fixture]);
  const browser=await chromium.launch(process.env.CHROME_BIN?{executablePath:process.env.CHROME_BIN}:{});
  const errors=[],checks=[];
  try{
    const page=await browser.newPage({viewport:{width:1440,height:900}});
    page.on('pageerror',error=>errors.push(error.message));
    const response=await page.goto(url,{timeout:120000});assert.equal(response.status(),200);
    await page.locator('#empty-connect').click();
    assert.deepEqual(await page.locator('#kind option').evaluateAll(nodes=>nodes.map(node=>node.value)),['zip']);
    await page.locator('#zip').setInputFiles({name:'mixed-repository.zip',mimeType:'application/zip',buffer:archive});
    await page.locator('#start').click();
    const frame=page.frameLocator('#map');
    await frame.locator('#status').filter({hasText:'source verified'}).waitFor({timeout:120000});
    const status=await frame.locator('#status').innerText();assert.match(status,/4 files/);
    assert.match(await page.locator('#summary').innerText(),/2 distinct call relationships/);
    checks.push('ZIP upload runs Python and TypeScript analysis and opens the verified source map');
    await page.locator('#doc-tab').click();assert.match(await page.locator('#doc').innerText(),/Structural components/);
    await page.locator('#map-tab').click();
    const mapUrl=await page.locator('#download-map').getAttribute('href');
    assert.equal((await page.request.get(new URL(mapUrl,url).href)).status(),200);
    assert.equal((await page.request.get(new URL(await page.locator('#download').getAttribute('href'),url).href)).status(),200);
    checks.push('Documentation, graph and portable map downloads are available');
    await page.reload();
    await page.frameLocator('#map').locator('#status').filter({hasText:'source verified'}).waitFor({timeout:120000});
    checks.push('Refreshing the tab restores the completed analysis');
    assert.equal((await page.request.get(new URL('/api/jobs/'+'0'.repeat(64),url).href)).status(),404);
    assert.deepEqual(errors,[]);
    await page.screenshot({path:path.join(evidence,'hosted-workspace.png')});
    const result={url,status:'passed',checks,page_errors:errors,verified_at:new Date().toISOString()};
    fs.writeFileSync(path.join(evidence,'checks.json'),JSON.stringify(result,null,2)+'\n');
    console.log(JSON.stringify(result));
  }finally{await browser.close();}
}
run().catch(error=>{console.error(error);process.exitCode=1;});
