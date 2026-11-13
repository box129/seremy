// Real generated Redux guide, source navigation and downloadable Markdown.
const {chromium}=require('playwright');
const {spawn,execFileSync}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const {selectRenderer}=require('./map-test-url.cjs');

async function run(){
  const root=path.resolve(__dirname,'../..'),evidence=path.resolve(process.argv[2]);
  fs.mkdirSync(evidence,{recursive:true});
  const server=spawn(process.env.PYTHON||'python',['-B','-m','seremy.server','--port','0','--output',path.join(evidence,'publications')],
    {cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});
  let browser,logs='';server.stderr.on('data',chunk=>{logs+=chunk;});
  const checks=[],errors=[];
  try{
    const localUrl=await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(new Error('Server startup timed out '+logs)),15000);
      server.stdout.on('data',chunk=>{const match=chunk.toString().match(/http:\/\/127\.0\.0\.1:\d+/);if(match){clearTimeout(timer);resolve(match[0]);}});
      server.on('exit',code=>{clearTimeout(timer);reject(new Error('Server exited '+code+' '+logs));});
    });
    const url=process.argv[3]||localUrl;
    browser=await chromium.launch(process.env.CHROME_BIN?{executablePath:process.env.CHROME_BIN}:{});
    const page=await browser.newPage({viewport:{width:1440,height:900}});
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(url,{timeout:120000});await page.locator('#empty-connect').click();
    const fixture=path.join(root,'seremy/fixtures/redux-slice');
    if(process.argv[3]){
      const archive=execFileSync(process.env.PYTHON||'python',['-B','-c',
        'import io,pathlib,sys,zipfile\nb=io.BytesIO()\nroot=pathlib.Path(sys.argv[1])\nwith zipfile.ZipFile(b,"w") as z:\n for f in root.rglob("*"):\n  if f.is_file(): z.write(f,f.relative_to(root).as_posix())\nsys.stdout.buffer.write(b.getvalue())',fixture]);
      await page.locator('#zip').setInputFiles({name:'redux-guide.zip',mimeType:'application/zip',buffer:archive});
    }else await page.locator('#value').fill(fixture);
    await page.locator('#start').click();
    const map=page.frameLocator('#map');
    await map.locator('#status').filter({hasText:'source verified'}).waitFor({timeout:60000});
    await selectRenderer(map);
    await page.locator('#doc-tab').click();
    const doc=page.locator('#doc');await doc.filter({hasText:'Call walkthroughs'}).waitFor();
    assert.match(await doc.innerText(),/`isAction` to `isPlainObject`/);
    const call=doc.getByRole('link').filter({hasText:'call site · src/utils/isAction.ts'}).first();
    const target=doc.getByRole('link').filter({hasText:'target declaration · src/utils/isPlainObject.ts'}).first();
    const citation=JSON.parse(decodeURIComponent((await call.getAttribute('href')).split('#seremy-source=')[1]));
    await call.click();await map.locator('#detail').filter({hasText:'isAction.ts'}).waitFor();
    const before=await map.locator('#world').getAttribute('transform');
    await page.locator('#doc-tab').click();await target.click();
    await map.locator('#detail').filter({hasText:'isPlainObject.ts'}).waitFor();
    await map.locator('#back').click();await map.locator('#detail').filter({hasText:'isAction.ts'}).waitFor();
    assert.equal(await map.locator('#world').getAttribute('transform'),before);
    checks.push('Redux walkthrough opens its call site and declaration, and Back restores the call camera');

    const unchanged=await map.locator('#world').getAttribute('transform');
    await page.evaluate(c=>document.querySelector('#map').contentWindow.postMessage({type:'seremy-document-source',citation:{...c,digest:'0'.repeat(64)}},'*'),citation);
    // A round trip through the frame observes handling of the preceding message.
    await map.locator('#world').evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    assert.equal(await map.locator('#world').getAttribute('transform'),unchanged);
    checks.push('A source citation from a different graph digest cannot change map focus');

    const mapUrl=await page.locator('#map').getAttribute('src');
    const downloadUrl=await page.locator('#download-doc').getAttribute('href');
    const response=await page.request.get(new URL(downloadUrl,url).href);
    const markdown=await response.text();
    assert.match(markdown,/Call walkthroughs/);assert.match(markdown,/map.html#seremy-source=/);
    fs.writeFileSync(path.join(evidence,'architecture.md'),markdown);
    const direct=await browser.newPage();direct.on('pageerror',error=>errors.push(error.message));
    const link=[...markdown.matchAll(/\]\((map\.html#seremy-source=[^)]+)\)/g)].map(match=>match[1]).find(link=>{
      const c=JSON.parse(decodeURIComponent(link.split('#seremy-source=')[1]));
      return c.file_id===citation.file_id&&c.role==='call_site';
    });
    assert.ok(link);
    await direct.goto(new URL(link,new URL(mapUrl,url)).href);
    await direct.locator('#detail').filter({hasText:'isAction.ts'}).waitFor();
    await direct.close();
    checks.push('Downloaded Markdown retains snapshot-bound links that open the standalone map');
    await page.locator('#doc-tab').click();await page.screenshot({path:path.join(evidence,'guide.png')});
    assert.deepEqual(errors,[]);
    const result={status:'passed',hosted_url:process.argv[3]||null,renderer:process.env.SEREMY_RENDERER||'svg',browser:browser.version(),checks,page_errors:errors};
    fs.writeFileSync(path.join(evidence,'checks.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
  }finally{if(browser)await browser.close();server.kill();}
}
run().catch(error=>{console.error(error);process.exitCode=1;});
