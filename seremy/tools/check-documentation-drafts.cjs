// Official SDK stdio requests, actual browser acknowledgements and review states.
const {chromium}=require('playwright');
const {spawn,execFileSync}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const {selectRenderer}=require('./map-test-url.cjs');

async function run(){
  const root=path.resolve(__dirname,'../..'),evidence=path.resolve(process.argv[2]);fs.mkdirSync(evidence,{recursive:true});
  const sdkPython=process.env.MCP_PYTHON||path.join(root,'.venv/Scripts/python.exe');
  const server=spawn(process.env.PYTHON||'python',['-B','-m','seremy.server','--port','0','--output',path.join(evidence,'publications')],
    {cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});
  let browser,logs='',probe=0;server.stderr.on('data',chunk=>{logs+=chunk;});
  const checks=[],errors=[];
  try{
    const url=await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(new Error('Server startup timed out '+logs)),15000);
      server.stdout.on('data',chunk=>{const match=chunk.toString().match(/http:\/\/127\.0\.0\.1:\d+/);if(match){clearTimeout(timer);resolve(match[0]);}});
      server.on('exit',code=>{clearTimeout(timer);reject(new Error('Server exited '+code+' '+logs));});
    });
    function sdk(tool,args){
      const file=path.join(evidence,'request-'+(++probe)+'.json');fs.writeFileSync(file,JSON.stringify([{tool,arguments:args}]));
      const response=JSON.parse(execFileSync(sdkPython,['-B',path.join(__dirname,'mcp_probe.py'),url,file],
        {cwd:root,windowsHide:true,encoding:'utf8',timeout:60000,maxBuffer:8*1024*1024}))[0];
      if(response.isError)return response;
      const value=response.structuredContent||JSON.parse(response.content[0].text);return value.result??value;
    }
    browser=await chromium.launch(process.env.CHROME_BIN?{executablePath:process.env.CHROME_BIN}:{});
    const page=await browser.newPage({viewport:{width:1440,height:900}});page.on('pageerror',error=>errors.push(error.message));
    await page.goto(url);await page.locator('#empty-connect').click();await page.locator('#value').fill(path.join(root,'seremy/fixtures/redux-slice'));await page.locator('#start').click();
    const map=page.frameLocator('#map');await map.locator('#status').filter({hasText:'source verified'}).waitFor({timeout:60000});await selectRenderer(map);
    const canonical=await map.locator('#fixture').textContent();
    await map.locator('#inspect').click();await map.locator('#mcp-tools summary').click();await map.locator('#connect-agent').click();
    await page.waitForFunction(async()=>{const r=await fetch('/api/mcp/views');return (await r.json()).some(v=>v.verified);});
    const active=(await (await page.request.get(url+'/api/mcp/views')).json()).find(v=>v.verified),identity={view_id:active.view_id,digest:active.digest};
    const listing=sdk('list_documentation_sections',identity);assert.ok(listing.sections.some(s=>s.section_id==='walkthroughs'));
    // Use the page containing isAction, independently selected by source path.
    let context,offset=0;
    do{
      context=sdk('read_documentation_section',{...identity,section_id:'walkthroughs',offset,limit:10});
      if(context.claims.some(c=>c.map_citations.some(site=>site.file==='src/utils/isAction.ts')))break;
      offset=context.next_offset;
    }while(offset!==null);
    const claim=context.claims.find(c=>c.map_citations.some(site=>site.file==='src/utils/isAction.ts'));assert.ok(claim);
    fs.writeFileSync(path.join(evidence,'section-context.json'),JSON.stringify(context,null,2));
    checks.push('A real stdio client lists sections, pages to Redux call evidence and receives source omissions and dependencies');
    let submission={request_id:'qualified-draft',context_digest:context.context_digest,
      statements:[{text:claim.text,kind:'projection',claim_ids:[claim.claim_id]},
                  {text:'Use the linked call site and declaration to investigate this static relationship.',kind:'explanation',claim_ids:[claim.claim_id]}],
      generation:{provider:null,model:null,prompt_version:'mechanics-fixture-v1',settings:null}};
    if(process.argv.includes('--model')){
      const target=path.join(evidence,'model-submission.json');
      if(fs.existsSync(target))throw new Error('Use a fresh evidence directory for the real model lane');
      console.log('MODEL_CONTEXT_READY '+path.join(evidence,'section-context.json'));
      const deadline=Date.now()+300000;
      while(!fs.existsSync(target)&&Date.now()<deadline)await new Promise(resolve=>setTimeout(resolve,500));
      assert.ok(fs.existsSync(target),'A real model submission must be supplied after reading the context');
      submission=JSON.parse(fs.readFileSync(target,'utf8'));
    }
    const receipt=sdk('submit_documentation_draft',{...identity,...submission});assert.equal(receipt.draft.accepted,false);
    assert.equal(receipt.draft.status,'review_required');assert.ok(receipt.draft.statements.some(s=>s.status==='review_required'));
    const article=map.locator('.documentation-draft').first();await article.filter({hasText:'Human review pending'}).waitFor();
    const retried=sdk('submit_documentation_draft',{...identity,...submission});assert.equal(retried.draft.draft_id,receipt.draft.draft_id);
    assert.equal(await map.locator('.documentation-draft').count(),1);
    const stored=sdk('read_documentation_draft',{...identity,request_id:submission.request_id});assert.equal(stored.draft.draft_id,receipt.draft.draft_id);
    assert.equal(stored.delivery,'acknowledged');
    fs.writeFileSync(path.join(evidence,'draft-receipt.json'),JSON.stringify(receipt,null,2));
    await page.locator('#doc-tab').click();await page.locator('#doc').filter({hasText:'Documentation draft'}).waitFor();await page.locator('#map-tab').click();
    await article.getByRole('button').filter({hasText:'src/utils/isPlainObject.ts:'}).first().click();await map.locator('#detail').filter({hasText:'isPlainObject.ts:5'}).waitFor();
    const download=page.waitForEvent('download');await article.getByRole('button',{name:'Download draft Markdown'}).click();
    const downloaded=await download;await downloaded.saveAs(path.join(evidence,'draft.md'));
    assert.equal(fs.readFileSync(path.join(evidence,'draft.md'),'utf8'),receipt.draft.markdown);
    checks.push('Submitted prose retains review status and reported provenance; one retry yields one visible draft, Docs, source focus and Markdown work');

    const rejected=sdk('submit_documentation_draft',{...identity,request_id:'unsupported-projection',context_digest:context.context_digest,
      statements:[{text:'isAction always runs isPlainObject in production and owns the business layer.',kind:'projection',claim_ids:[claim.claim_id]}],generation:{}});
    assert.equal(rejected.draft.status,'rejected');await map.locator('.documentation-draft').filter({hasText:'projection_text_mismatch'}).waitFor();
    const bad=sdk('submit_documentation_draft',{...identity,request_id:'foreign-ref',context_digest:context.context_digest,
      statements:[{text:'wrong',kind:'explanation',claim_ids:['foreign-claim']}],generation:{}});assert.equal(bad.isError,true);
    checks.push('Unsupported runtime and ownership projection is rejected and a foreign claim reference fails through the real protocol');

    await map.locator('#arrangement-tools').evaluate(n=>n.open=true);await map.locator('#save-view').click();
    await map.locator('#connect-agent').click();await page.waitForFunction(async id=>(await (await fetch('/api/mcp/views')).json()).some(v=>v.view_id===id&&!v.verified),active.view_id);
    assert.equal(sdk('read_documentation_draft',{...identity,request_id:submission.request_id}).isError,true);
    await page.locator('#map').evaluate(n=>n.contentWindow.location.reload());await map.locator('#status').filter({hasText:'source verified'}).waitFor();
    await map.locator('#inspect').click();await map.locator('#arrangement-tools').evaluate(n=>n.open=true);await map.locator('#restore-view').click();
    await map.locator('#mcp-tools').evaluate(n=>n.open=true);assert.equal(await map.locator('.documentation-draft').count(),2);
    assert.equal(await map.locator('#fixture').textContent(),canonical);
    await page.screenshot({path:path.join(evidence,'drafts.png')});assert.deepEqual(errors,[]);
    checks.push('Revoked sharing blocks draft reads; Save/Restore retains review labels and citations without changing the canonical graph');
    const result={status:'passed',model_lane:process.argv.includes('--model')?'Codex model with SDK stdio bridge':'authored mechanics fixture',renderer:process.env.SEREMY_RENDERER||'svg',browser:browser.version(),checks,page_errors:errors};
    fs.writeFileSync(path.join(evidence,'checks.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
  }finally{if(browser)await browser.close();server.kill();}
}
run().catch(error=>{console.error(error);process.exitCode=1;});
