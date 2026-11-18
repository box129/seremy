// Exercise the hosted Redux entry point with a simulated provider, or inspect
// the deployed button without making a paid request when a URL is supplied.
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');

async function main(){
  const root=path.resolve(__dirname,'../..');
  const evidence=path.resolve(process.argv[2]);fs.mkdirSync(evidence,{recursive:true});
  const remote=process.argv[3];let server,browser,logs='';
  const checks=[],errors=[];
  try{
    let url=remote;
    if(!remote){
      const code=`from wsgiref.simple_server import make_server\nfrom seremy.hosted import HostedApplication, make_app\nfrom seremy.tests.test_hosted_drafts import Provider\nservice=HostedApplication(${JSON.stringify(path.join(evidence,'publications'))},draft_provider=Provider())\nserver=make_server('127.0.0.1',0,make_app(service))\nprint('http://127.0.0.1:'+str(server.server_port),flush=True)\nserver.serve_forever()`;
      server=spawn(process.env.PYTHON||'python',['-B','-c',code],{cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});
      server.stderr.on('data',chunk=>logs+=chunk);
      url=await new Promise((resolve,reject)=>{
        const timeout=setTimeout(()=>reject(new Error('Local server did not start '+logs)),15000);
        server.stdout.on('data',chunk=>{const match=String(chunk).match(/http:\/\/127\.0\.0\.1:\d+/);if(match){clearTimeout(timeout);resolve(match[0]);}});
        server.on('exit',code=>{clearTimeout(timeout);reject(new Error('Server exited '+code+' '+logs));});
      });
    }
    browser=await chromium.launch(process.env.CHROME_BIN?{executablePath:process.env.CHROME_BIN}:{});
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    page.on('pageerror',error=>errors.push(error.message));
    assert.equal((await page.goto(url,{timeout:120000})).status(),200);
    await page.locator('#try-example').click();
    const frame=page.frameLocator('#map');
    await frame.locator('#status').filter({hasText:'source verified'}).waitFor({state:'attached',timeout:120000});
    assert.match(await page.locator('#connect').innerText(),/Redux example/);
    assert.match(await page.locator('#summary').innerText(),/17 source files processed/);
    const report=await page.locator('#map').getAttribute('src');
    assert.match(report,/^\/reports\/[0-9a-f]{64}\/map.html$/);
    assert.equal(await page.locator('#map').getAttribute('srcdoc'),null);
    const publicState=await (await page.request.get(new URL(report.replace('/reports/','/api/jobs/').replace('/map.html',''),url).href)).json();
    assert.equal(publicState.example,true);assert.equal(publicState.generation_token,undefined);
    checks.push('Try Redux creates a completed live report and excludes the capability from public status');
    assert.equal(await page.getByRole('button',{name:'Generate documentation',exact:true}).count(),1);
    assert.match(await page.locator('#status').innerText(),/Analysis complete/);
    assert.equal(await page.getByRole('complementary',{name:'Guided exploration'}).isVisible(),false);
    await page.locator('#generate-documentation').click();
    await frame.getByRole('combobox',{name:'Documentation type'}).waitFor();
    await frame.getByRole('button',{name:'Close documentation request'}).press('Escape');
    await page.waitForFunction(()=>document.activeElement?.id==='generate-documentation');
    checks.push('Documentation uses consistent terminology, analysis has its own status, tour is optional and Escape restores launcher focus');
    await frame.locator('#toggle-search').click();await frame.locator('#search').fill('isAction');
    assert.equal(await frame.locator('#files').inputValue(),'utils/isAction.ts');
    await frame.locator('#search').press('Enter');
    assert.match(await frame.locator('#detail').innerText(),/utils\/isAction.ts/);
    await page.setViewportSize({width:390,height:844});
    await page.reload();
    await frame.locator('#status').filter({hasText:'source verified'}).waitFor({state:'attached',timeout:120000});
    assert.equal(await frame.locator('#repository').isVisible(),false);
    await page.locator('#mobile-actions summary').click();
    assert.equal(await page.locator('#mobile-actions').getByRole('button',{name:'Save on this device',exact:true}).isVisible(),true);
    await page.locator('#mobile-actions summary').click();
    const map=frame.locator('#map'),world=frame.locator('#world');
    const rect=await map.boundingBox(),x=rect.x+rect.width/2,y=rect.y+rect.height/2;
    const matrix=async()=>((await world.getAttribute('transform')).match(/-?[\d.]+/g).map(Number));
    const before=await matrix();
    await map.evaluate(e=>{window.touchAudit=[];for(const type of ['pointerdown','pointermove','pointerup','pointercancel','lostpointercapture'])e.addEventListener(type,event=>window.touchAudit.push([type,event.pointerId,event.clientX,event.clientY]));});
    const cdp=await page.context().newCDPSession(page);
    const touch=async(type,points)=>cdp.send('Input.dispatchTouchEvent',{type,touchPoints:points.map(([id,x,y])=>({id,x,y,radiusX:5,radiusY:5,force:1}))});
    await touch('touchStart',[[1,x-40,y],[2,x+40,y]]);
    await touch('touchMove',[[1,x-80,y],[2,x+80,y]]);
    const after=await matrix();assert.ok(Math.abs(after[2]/before[2]-2)<.02);
    const localX=x-rect.x,localY=y-rect.y;
    assert.ok(Math.hypot((localX-before[0])/before[2]*after[2]+after[0]-localX,(localY-before[1])/before[2]*after[2]+after[1]-localY)<1);
    await touch('touchEnd',[[2,x+80,y]]);
    const beforePan=await world.getAttribute('transform');
    await touch('touchMove',[[1,x-60,y+20]]);
    await page.waitForFunction(old=>document.querySelector('#map').contentDocument.querySelector('#world').getAttribute('transform')!==old,beforePan,{timeout:5000});
    const panned=await matrix();assert.ok(Math.abs(panned[0]-after[0]-20)<1,JSON.stringify({before,after,panned,events:await map.evaluate(()=>window.touchAudit)}));assert.ok(Math.abs(panned[1]-after[1]-20)<1);
    await touch('touchCancel',[]);
    await map.focus();await map.press('+');assert.ok((await matrix())[2]>panned[2]);
    await page.screenshot({path:path.join(evidence,'hci-mobile-map.png')});
    checks.push('Exact symbol search prioritizes its file; mobile starts with the drawer closed and preserves save access; Chromium touch pinch anchors and transitions to pan, cancellation and keyboard zoom work');
    await page.setViewportSize({width:1440,height:1000});
    // Generation/save checks below use desktop utilities, not the mobile menu.
    // The guided tour is nonmodal. Close it before entering the request.
    if(await page.locator('#tour-close').count())await page.locator('#tour-close').click();
    await page.locator('#generate-documentation').click();
    const submit=frame.locator('#copy-documentation-request');
    await submit.filter({hasText:'Generate documentation'}).waitFor();
    await submit.waitFor({state:'visible'});
    await page.waitForFunction(()=>{
      const button=document.querySelector('#map').contentDocument?.querySelector('#copy-documentation-request');
      return button&&!button.disabled;
    },null,{timeout:15000});
    await frame.locator('#documentation-scope').selectOption({label:'utils/isAction.ts'});
    await frame.locator('#documentation-purpose').selectOption('walkthrough');
    await frame.locator('#documentation-question').fill('How does isAction check an action?');
    await page.screenshot({path:path.join(evidence,'redux-generation-enabled.png')});
    checks.push('The Redux request form enables generation and offers the normal file scope and page type');
    if(!remote){
      await submit.click();
      await page.locator('#doc').filter({hasText:'This file defines a function and calls it.'}).waitFor({timeout:30000});
      assert.match(await page.locator('#doc').innerText(),/Human review pending/);
      await page.locator('#save-device').click();
      await page.locator('#status').filter({hasText:'Saved on this device'}).waitFor();
      await page.screenshot({path:path.join(evidence,'redux-generated-simulated-page.png')});
      checks.push('A simulated provider draft arrives in Documentation with review status and can be saved on the device');
      await page.reload();await page.locator('#history').click();
      await page.getByRole('button',{name:'Open saved Redux example (bundled source)',exact:true}).click();
      await frame.locator('#status').filter({hasText:'source verified'}).waitFor({timeout:15000});
      await page.locator('#generate-documentation').click();
      await page.waitForFunction(()=>document.querySelector('#map').contentDocument?.querySelector('#documentation-request-status')?.textContent.includes('Analyze this repository again'));
      assert.equal(await frame.locator('#copy-documentation-request').isDisabled(),true);
      checks.push('A device-saved copy remains readable without granting new generation access');
    }else{
      checks.push('No model request was submitted on the deployed service');
    }
    assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(evidence,'browser-checks.json'),JSON.stringify({url,provider:remote?'live configuration; no inference':'simulated',checks,errors},null,2));
    console.log(JSON.stringify({checks,errors},null,2));
  }finally{
    if(browser)await browser.close();
    if(server)server.kill();
  }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
