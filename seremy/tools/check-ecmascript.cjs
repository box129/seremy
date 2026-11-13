// Full local/hosted JSX-source journey against independently specified call truth.
const {chromium}=require('playwright');
const {spawn,execFileSync}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path');
const assert=require('node:assert/strict');
const {selectRenderer}=require('./map-test-url.cjs');

async function run(){
  const evidence=path.resolve(process.argv[2]),hostedUrl=process.argv[3];fs.mkdirSync(evidence,{recursive:true});
  const root=path.resolve(__dirname,'../..'),fixture=path.join(root,'seremy/fixtures/ecmascript-slice'),truth=JSON.parse(fs.readFileSync(path.join(fixture,'truth.json'),'utf8'));
  let server,browser,url=hostedUrl,logs='';const checks=[],errors=[],renderers=[],digests=[];
  try{
    if(!url){
      server=spawn(process.env.PYTHON||'python',['-B','-m','seremy.server','--port','0','--output',path.join(evidence,'publications')],{cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});server.stderr.on('data',data=>{logs+=data;});
      url=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('Server startup timeout '+logs)),15000);server.on('exit',code=>{clearTimeout(timer);reject(new Error('Server exited '+code+' '+logs));});server.stdout.on('data',data=>{const match=String(data).match(/http:\/\/127\.0\.0\.1:\d+/);if(match){clearTimeout(timer);resolve(match[0]);}});});
    }
    browser=await chromium.launch({...(process.env.CHROME_BIN?{executablePath:process.env.CHROME_BIN}:{}),args:['--use-angle=d3d11','--enable-webgl','--ignore-gpu-blocklist']});
    const archive=hostedUrl?execFileSync(process.env.PYTHON||'python',['-B','-c','import io,pathlib,sys,zipfile\nb=io.BytesIO()\nroot=pathlib.Path(sys.argv[1])\nwith zipfile.ZipFile(b,"w") as z:\n for f in root.iterdir():\n  if f.is_file(): z.write(f,"repo/"+f.name)\nsys.stdout.buffer.write(b.getvalue())',fixture]):null;
    for(const renderer of ['svg','pixi']){
      process.env.SEREMY_RENDERER=renderer;
      const page=await browser.newPage({viewport:{width:1440,height:900}});page.on('pageerror',error=>errors.push(error.message));
      assert.equal((await page.goto(url,{timeout:120000})).status(),200);await page.locator('#empty-connect').click();
      assert.match(await page.locator('#input-profile').innerText(),/\.js, \.jsx and \.tsx/);
      if(hostedUrl)await page.locator('#zip').setInputFiles({name:'ecmascript-fixture.zip',mimeType:'application/zip',buffer:archive});else await page.locator('#value').fill(fixture);
      await page.locator('#start').click();const frame=page.frameLocator('#map');await frame.locator('#status').filter({hasText:'source verified'}).waitFor({timeout:120000});await selectRenderer(frame);
      const rendering=await frame.locator('body').evaluate(()=>window.__seremyRendererInfo());assert.equal(rendering.engine,renderer);renderers.push(rendering);
      const canonical=await frame.locator('#fixture').textContent(),data=JSON.parse(canonical);
      const basename=file=>file.split('/').at(-1),file=name=>Object.keys(data.files).find(file=>basename(file)===name);
      assert.equal(Object.keys(data.files).length,5);assert.equal(data.bundle.profile,'seremy-local-ecmascript-v0.1');assert.equal(data.coverage.s02.complete,5);
      assert.equal(data.coverage.s03.attempted_count,9);assert.equal(data.coverage.s03.candidate_count,22);assert.equal(data.edges.length,3);
      const actual=data.edges.map(edge=>({source_file:basename(edge.from.file),source_name:data.entities.find(entity=>entity.file_id===edge.from.file&&entity.decl_span[0]<=edge.from.start&&entity.decl_span[1]>=edge.from.end).name,
        target_file:basename(edge.to.file),target_name:new TextDecoder().decode(new TextEncoder().encode(data.files[edge.to.file]).slice(edge.to.start,edge.to.end)),
        token:new TextDecoder().decode(new TextEncoder().encode(data.files[edge.from.file]).slice(edge.from.start,edge.from.end)),line:new TextDecoder().decode(new TextEncoder().encode(data.files[edge.from.file]).slice(0,edge.from.start)).split('\n').length}));
      assert.deepEqual(actual.sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b))),truth.relationships.sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b))));
      digests.push(data.bundle.content_digest);await frame.locator('#show-coverage').click();assert.match(await frame.locator('#analysis-coverage').innerText(),/JSX tags are syntax observations/);assert.match(await frame.locator('#analysis-coverage').innerText(),/\.jsx, \.tsx/);
      checks.push(renderer+': actual local/ZIP ingestion selects the named profile, five sources and exactly the independently specified three direct-call sites');

      const edge=data.edges.find(edge=>edge.from.file===file('App.tsx')&&edge.to.file===file('helper.js'));
      await frame.locator('#edges').selectOption(edge.id);await frame.locator('#origin').click();
      const targetVisibility=frame.getByRole('checkbox',{name:'Show '+edge.to.file+' on map',exact:true});await targetVisibility.uncheck();const camera=await frame.locator('#world').getAttribute('transform');
      await frame.locator('#target').click();assert.equal(await targetVisibility.isChecked(),true);assert.match(await frame.locator('#detail').innerText(),/helper.js:2.*original/);
      const alignment=await frame.locator('body').evaluate((_body,span)=>{
        const data=JSON.parse(document.querySelector('#fixture').textContent),prefix=new TextDecoder().decode(new TextEncoder().encode(data.files[span.file]).slice(0,span.start)),lines=prefix.split(/\r\n|\n/);
        const row=[...document.querySelectorAll('.code[data-file]')].find(node=>node.dataset.file===span.file&&Number(node.dataset.line)===lines.length),index=lines.at(-1).length-Number(row.dataset.renderStart);
        return Math.abs(Number(document.querySelector('.source-focus').getAttribute('x'))-row.querySelector('tspan[x]').getStartPositionOfChar(index).x);
      },edge.to);assert.ok(alignment<1);
      await frame.locator('#back').click();assert.equal(await targetVisibility.isChecked(),false);assert.equal(await frame.locator('#world').getAttribute('transform'),camera);
      await frame.locator('#arrangement-tools').evaluate(node=>node.open=true);await frame.locator('#save-view').click();
      await page.locator('#doc-tab').click();await page.locator('#doc').filter({hasText:'original'}).waitFor();assert.match(await page.locator('#doc').innerText(),/original/);await page.locator('#map-tab').click();assert.equal(await targetVisibility.isChecked(),false);
      const graph=await (await page.request.get(new URL(await page.locator('#download').getAttribute('href'),url).href)).json();assert.equal(graph.bundle.content_digest,data.bundle.content_digest);
      checks.push(renderer+': TSX-to-JS alias navigation aligns exact Unicode-prefixed source bytes; Back, docs and graph downloads retain the same evidence and working set');

      await frame.locator('#outcome-tools').evaluate(node=>node.open=true);const tag=data.outcomes.find(record=>record.candidate_kind==='jsx_tag'&&record.name==='Child');assert.ok(tag);
      await frame.locator('#outcomes').selectOption(tag.candidate_id);assert.equal(await frame.locator('#target').isDisabled(),true);assert.match(await frame.locator('#outcome-detail').innerText(),/NOT_PROCESSED.*jsx_runtime_semantics_outside_profile/);
      await frame.locator('#origin').click();assert.match(await frame.locator('#detail').innerText(),/App.tsx:4.*Child/);
      const unsupported=data.outcomes.find(record=>record.reason==='binding_reassigned_in_snapshot');await frame.locator('#outcomes').selectOption(unsupported.candidate_id);
      assert.equal(await frame.locator('#target').isDisabled(),true);assert.match(await frame.locator('#outcome-detail').innerText(),/UNSUPPORTED.*binding_reassigned_in_snapshot/);
      assert.equal(await frame.locator('#fixture').textContent(),canonical);
      checks.push(renderer+': JSX component tags and reassigned call targets expose their recorded limits and cannot invent target navigation or runtime edges');

      if(hostedUrl)await page.reload();else{
        const mapUrl=new URL(await page.locator('#map').getAttribute('src'),url).href;
        await Promise.all([page.waitForEvent('framenavigated',{predicate:frame=>frame.url()===mapUrl}),page.locator('#map').evaluate(node=>node.contentWindow.location.reload())]);
      }
      await page.frameLocator('#map').locator('#status').filter({hasText:'source verified'}).waitFor({timeout:120000});await selectRenderer(page.frameLocator('#map'));
      await frame.locator('#inspect').click();await frame.locator('#arrangement-tools').evaluate(node=>node.open=true);await frame.locator('#restore-view').click();
      if(renderer==='pixi')await frame.locator('body[data-renderer=pixi]').waitFor();assert.equal(await targetVisibility.isChecked(),false);assert.equal(await frame.locator('#edges').inputValue(),edge.id);
      for(const viewport of [{width:1440,height:900},{width:1280,height:800}]){await page.setViewportSize(viewport);await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth||document.documentElement.scrollHeight>innerHeight),false);}
      await page.screenshot({path:path.join(evidence,renderer+'-ecmascript.png')});
      checks.push(renderer+': the extended-profile snapshot restores its saved working set and exact selection after refresh at both desktop sizes');
      await page.close();
    }
    assert.deepEqual(errors,[]);const result={status:'passed',url,hosted:!!hostedUrl,browser:browser.version(),executable:process.env.CHROME_BIN||'playwright-chromium',renderers,digests,checks,page_errors:errors,verified_at:new Date().toISOString()};fs.writeFileSync(path.join(evidence,'checks.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
  }finally{if(browser)await browser.close();if(server)server.kill();}
}
run().catch(error=>{console.error(error);process.exitCode=1;});
