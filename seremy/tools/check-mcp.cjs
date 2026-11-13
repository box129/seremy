// Real local launcher, browser map and official SDK stdio client.
const {chromium}=require('playwright');
const {spawn,execFileSync}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const {selectRenderer}=require('./map-test-url.cjs');

async function run(){
  const root=path.resolve(__dirname,'../..'),evidence=path.resolve(process.argv[2]);
  fs.mkdirSync(evidence,{recursive:true});
  const sdkPython=process.env.MCP_PYTHON||path.join(root,'.venv','Scripts','python.exe');
  const server=spawn(process.env.PYTHON||'python',['-B','-m','seremy.server','--port','0','--output',path.join(evidence,'publications')],
    {cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});
  let browser,logs='',probe=0;
  server.stderr.on('data',chunk=>{logs+=chunk;});
  const checks=[],errors=[];
  try{
    const url=await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(new Error('Server startup timed out '+logs)),15000);
      server.stdout.on('data',chunk=>{const match=chunk.toString().match(/http:\/\/127\.0\.0\.1:\d+/);if(match){clearTimeout(timer);resolve(match[0]);}});
      server.on('exit',code=>{clearTimeout(timer);reject(new Error('Server exited '+code+' '+logs));});
    });
    function sdk(actions){
      const file=path.join(evidence,'mcp-requests-'+(++probe)+'.json');
      fs.writeFileSync(file,JSON.stringify(actions));
      return JSON.parse(execFileSync(sdkPython,['-B',path.join(__dirname,'mcp_probe.py'),url,file],
        {cwd:root,windowsHide:true,encoding:'utf8',timeout:60000,maxBuffer:16*1024*1024}));
    }
    function result(response){
      assert.equal(response.isError||false,false,JSON.stringify(response));
      const value=response.structuredContent||JSON.parse(response.content[0].text);
      return value.result??value;
    }
    browser=await chromium.launch(process.env.CHROME_BIN?{executablePath:process.env.CHROME_BIN}:{});
    const page=await browser.newPage({viewport:{width:1440,height:900}});
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(url);
    await page.locator('#empty-connect').click();
    await page.locator('#value').fill(path.join(root,'seremy','fixtures','redux-slice'));
    await page.locator('#start').click();
    const map=page.frameLocator('#map');
    await map.locator('#status').filter({hasText:'source verified'}).waitFor({timeout:60000});
    await selectRenderer(map);
    const canonical=await map.locator('#fixture').textContent(),data=JSON.parse(canonical);
    const edge=data.edges.find(edge=>edge.from.file==='src/utils/isAction.ts'&&edge.to.file==='src/utils/isPlainObject.ts');
    await map.locator('#inspect').click();await map.locator('#edges').selectOption(edge.id);
    await map.locator('#origin').click();
    await map.locator('#mcp-tools summary').click();await map.locator('#connect-agent').click();
    await page.waitForFunction(async()=>{const response=await fetch('/api/mcp/views');return (await response.json()).some(view=>view.verified);});
    const views=await (await page.request.get(url+'/api/mcp/views')).json();
    const active=views.find(view=>view.verified),identity={view_id:active.view_id,digest:active.digest};
    const responses=sdk([{tool:'list_tools'},{tool:'list_views'},{tool:'get_selection',arguments:identity},{tool:'read_documentation',arguments:identity}]);
    assert.ok(responses[0].tools.some(tool=>tool.name==='focus_source'));
    assert.ok(result(responses[1]).some(view=>view.view_id===active.view_id));
    const context=result(responses[2]),documentation=result(responses[3]);
    assert.equal(context.connection.target.name,'isPlainObject');
    assert.equal(context.citations[0].line,6);assert.equal(context.citations[1].line,5);
    assert.equal(context.digest,active.digest);
    assert.ok(documentation.claims.some(claim=>claim.kind==='relationship'));
    assert.ok(documentation.claims.some(claim=>claim.map_citations?.length>0));
    fs.writeFileSync(path.join(evidence,'selection-evidence.json'),JSON.stringify(context,null,2));
    checks.push('A real stdio MCP client discovers tools and reads selected Redux evidence and validated documentation');

    const second=await browser.newPage();second.on('pageerror',error=>errors.push(error.message));
    await second.goto(new URL(await page.locator('#map').getAttribute('src'),url).href);
    await second.locator('#status').filter({hasText:'source verified'}).waitFor();
    await selectRenderer(second);
    await second.locator('#inspect').click();await second.locator('#mcp-tools summary').click();await second.locator('#connect-agent').click();
    const otherCamera=await second.locator('#world').getAttribute('transform');
    const span=context.citations[1],source=context.citations[0];
    const targetVisibility=map.getByRole('checkbox',{name:'Show '+span.file+' on map',exact:true});
    await targetVisibility.uncheck();assert.equal(await targetVisibility.isChecked(),false);
    const commands=sdk([{tool:'read_source',arguments:{...identity,file:source.file,start:source.start,end:source.end}},
      {tool:'get_selection',arguments:{...identity,digest:'stale-snapshot'}},
      {tool:'focus_source',arguments:{...identity,file:span.file,start:span.start,end:span.end}}]);
    assert.equal(result(commands[0]).text,'isPlainObject');
    assert.equal(commands[1].isError,true);
    assert.match(commands[1].content[0].text,/Stale or unverified/);
    const queued=result(commands[2]);assert.equal(queued.status,'queued');
    await map.locator('#detail').filter({hasText:'isPlainObject.ts:5'}).waitFor();
    await page.waitForFunction(async({id,sequence})=>{
      const views=await (await fetch('/api/mcp/views')).json();return views.some(view=>view.view_id===id&&view.last_applied_command>=sequence);
    },{id:active.view_id,sequence:queued.sequence});
    assert.equal(await targetVisibility.isChecked(),true);
    assert.equal(await second.locator('#world').getAttribute('transform'),otherCamera);
    await map.locator('#back').click();assert.equal(await map.locator('#edges').inputValue(),edge.id);
    assert.equal(await targetVisibility.isChecked(),false);
    checks.push('Source reading and stale-snapshot rejection work; acknowledged focus reveals a hidden target only in the intended view and Back restores visibility');

    const text='isAction calls isPlainObject on the action value. The recorded call is statically bound, with caller and declaration evidence cited below.';
    result(sdk([{tool:'add_agent_note',arguments:{...identity,text,citations:context.citations}}])[0]);
    await map.locator('#agent-notes').filter({hasText:text}).waitFor();
    assert.equal(await map.locator('#agent-notes strong').textContent(),'Agent annotation');
    await map.locator('#agent-notes button').first().click();
    await map.locator('#detail').filter({hasText:'isAction.ts:6'}).waitFor();
    await page.screenshot({path:path.join(evidence,'agent-note.png')});
    await map.locator('#arrangement-tools summary').click();await map.locator('#save-view').click();
    await map.locator('#view-status').filter({hasText:'View saved'}).waitFor();
    await map.locator('#connect-agent').click();
    await page.waitForFunction(async id=>{const views=await (await fetch('/api/mcp/views')).json();return views.some(view=>view.view_id===id&&!view.verified);},active.view_id);
    const refused=sdk([{tool:'get_selection',arguments:identity}])[0];assert.equal(refused.isError,true);
    assert.match(refused.content[0].text,/Stale or unverified/);
    await page.locator('#map').evaluate(node=>node.contentWindow.location.reload());
    await map.locator('#status').filter({hasText:'source verified'}).waitFor();
    await map.locator('#inspect').click();await map.locator('#arrangement-tools summary').click();await map.locator('#restore-view').click();
    await map.locator('#mcp-tools summary').click();
    if(process.env.SEREMY_RENDERER==='pixi')await map.locator('body[data-renderer=pixi]').waitFor();
    assert.equal(await map.locator('#agent-notes p').textContent(),text);
    assert.equal(await map.locator('#fixture').textContent(),canonical);
    checks.push('Cited agent annotations focus source, persist in saved views and remain distinct from graph evidence; stopping sharing revokes access');
    await second.locator('#connect-agent').click();
    assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(evidence,'checks.json'),JSON.stringify({status:'passed',checks,page_errors:errors},null,2)+'\n');
    console.log(JSON.stringify({status:'passed',checks}));
  }finally{if(browser)await browser.close();server.kill();}
}
run().catch(error=>{console.error(error);process.exitCode=1;});
