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
    await frame.locator('#status').filter({hasText:'source verified'}).waitFor({timeout:120000});
    assert.match(await page.locator('#connect').innerText(),/Redux example/);
    assert.match(await page.locator('#summary').innerText(),/17 source files processed/);
    const report=await page.locator('#map').getAttribute('src');
    assert.match(report,/^\/reports\/[0-9a-f]{64}\/map.html$/);
    assert.equal(await page.locator('#map').getAttribute('srcdoc'),null);
    const publicState=await (await page.request.get(new URL(report.replace('/reports/','/api/jobs/').replace('/map.html',''),url).href)).json();
    assert.equal(publicState.example,true);assert.equal(publicState.generation_token,undefined);
    checks.push('Try Redux creates a completed live report and excludes the capability from public status');
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
