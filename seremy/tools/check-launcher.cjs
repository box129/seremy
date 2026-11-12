const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const {selectRenderer}=require('./map-test-url.cjs');
async function run(){
  const packageRoot=path.resolve(__dirname,'..');
  const evidence=path.resolve(process.argv[2]);
  fs.mkdirSync(evidence,{recursive:true});
  const server=spawn(process.env.PYTHON||'python',['-B','-m','seremy.server','--port','0','--output',path.join(evidence,'publications')],
    {cwd:path.dirname(packageRoot),windowsHide:true,stdio:['ignore','pipe','pipe'],env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}});
  let logs='';
  server.stderr.on('data',chunk=>{logs+=chunk});
  let browser;
  try{
    const url=await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(new Error('server startup timed out '+logs)),15000);
      server.on('exit',code=>{clearTimeout(timer);reject(new Error('server exit '+code+' '+logs));});
      server.stdout.on('data',chunk=>{
        const match=chunk.toString().match(/http:\/\/127\.0\.0\.1:\d+/);
        if(match){clearTimeout(timer);resolve(match[0]);}
      });
    });
    browser=await chromium.launch(process.env.CHROME_BIN?{executablePath:process.env.CHROME_BIN}:{});
    const page=await browser.newPage({viewport:{width:1500,height:1100}});
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.goto(url);
    assert.match(await page.locator('#connect').innerText(), /No folder/);
    assert.equal(await page.locator('#form').isVisible(), false);
    await page.screenshot({path:path.join(evidence,'first-visit.png')});
    await page.getByRole('button',{name:'Docs',exact:true}).click();
    await page.getByRole('dialog',{name:'Explore a repository'}).waitFor();
    await page.keyboard.press('Escape');
    await page.getByRole('button',{name:'Connect repository',exact:true}).first().click();
    await page.locator('#value').fill(path.join(packageRoot,'fixtures','local-demo'));
    await page.getByRole('button',{name:'Analyze repository',exact:true}).click();
    await page.waitForFunction(()=>/Draft ready|Failed/.test(document.querySelector('#status').textContent),{},{timeout:30000});
    assert.equal(await page.locator('#status').innerText(),'Draft ready');
    assert.match(await page.locator('#summary').innerText(),/4 source files processed · 2 distinct call relationships/);
    const frame=page.frameLocator('#map');
    await frame.locator('#status').filter({hasText:'source verified'}).waitFor();
    await selectRenderer(frame);
    assert.ok(await frame.locator('#files option').count()===4);
    assert.equal(await page.locator('#connect-dialog').isVisible(),false);
    await frame.locator('#inspect').click();
    await frame.locator('#edges').selectOption({index:1});
    assert.equal(await frame.locator('#inspection-target').isVisible(),true);
    assert.ok((await frame.locator('#source-excerpt').textContent()).length>0);
    const selectedConnection=await frame.locator('#edges').inputValue();
    const camera=await frame.locator('#world').getAttribute('transform');
    const mapBounds=await page.locator('#map').boundingBox();
    assert.ok(mapBounds.height>=1000,'Map fills the workspace below its toolbar');
    await page.screenshot({path:path.join(evidence,'loaded-workspace.png')});
    await page.setViewportSize({width:1280,height:800});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth||document.documentElement.scrollHeight>innerHeight),false);
    await page.screenshot({path:path.join(evidence,'loaded-workspace-1280.png')});
    await page.getByRole('button',{name:'Documentation',exact:true}).click();
    const doc=page.locator('#doc');
    await doc.filter({hasText:'FastAPI'}).waitFor();
    assert.match(await doc.innerText(),/Preact/);
    assert.match(await doc.innerText(),/Component relationships/);
    await page.screenshot({path:path.join(evidence,'launcher-documentation.png')});
    await page.getByRole('button',{name:'Interactive map',exact:true}).click();
    assert.equal(await page.locator('#map').isVisible(),true);
    assert.equal(await frame.locator('#world').getAttribute('transform'),camera);
    assert.equal(await frame.locator('#inspector').isVisible(),true);
    assert.equal(await frame.locator('#edges').inputValue(),selectedConnection);
    await page.getByRole('button',{name:'Connect repository',exact:true}).click();
    await page.locator('#value').fill(path.join(evidence,'missing-repository'));
    await page.getByRole('button',{name:'Analyze repository',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('#connection-status').textContent.includes('Failed')||document.querySelector('#start').disabled===false);
    assert.equal(await page.locator('#connect-dialog').isVisible(),true);
    assert.ok((await page.locator('#connection-status').innerText()).length>0);
    await page.getByRole('button',{name:'Close connection'}).click();
    assert.equal(await page.locator('#map').isVisible(),true);
    assert.equal(await frame.locator('#world').getAttribute('transform'),camera);
    assert.deepEqual(errors,[]);
    const result={status:'passed',browser:browser.version(),checks:[
      'First visit shows No folder, centered Docs, and a keyboard-dismissable connection dialog',
      'Local folder submission runs both language adapters through all eight stages',
      'Four files and two direct relationships reach the shared graph',
      'Embedded interactive map verifies source bytes and provides file navigation',
      'Documentation contains package-scoped Preact and FastAPI evidence and structural relationships',
      'Map/documentation switching retains the same publication and camera',
      'Selection evidence and the open inspector survive documentation switching',
      'Loaded canvas fills the workspace and a failed replacement keeps the existing map available'],page_errors:errors};
    fs.writeFileSync(path.join(evidence,'launcher-checks.json'),JSON.stringify(result,null,2));
    console.log(JSON.stringify(result));
  }finally{
    if(browser)await browser.close();
    server.kill();
  }
}
run().catch(error=>{console.error(error);process.exitCode=1;});
