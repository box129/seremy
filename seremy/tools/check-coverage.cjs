// Exercise real empty/limited analyses and failed replacement through the launcher.
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const assert=require('node:assert/strict');

async function run(){
  const evidence=path.resolve(process.argv[2]);fs.mkdirSync(evidence,{recursive:true});
  const input=fs.mkdtempSync(path.join(os.tmpdir(),'seremy-coverage-'));
  const fixtures={unsupported:{'entry.js':'export function start() {}','view.tsx':'export const view = <div/>;','README.md':'An unsupported-only repository'},
    limited:{'valid.py':'def start(client):\n    return client.fetch()\n','broken.py':'def broken(:\n','partial.ts':'export function partial() { return missing( ; }','encoding.py':Buffer.from([255,254])},
    isolated:{'single.py':'def identity(value):\n    return value\n'},unreadable:{'encoding.py':Buffer.from([255,254])},skipped:{'oversized.py':'#'+'x'.repeat(1024*1024)},empty:{}};
  for(const [name,files] of Object.entries(fixtures)){
    fs.mkdirSync(path.join(input,name));for(const [filename,text] of Object.entries(files))fs.writeFileSync(path.join(input,name,filename),text);
  }
  const server=spawn(process.env.PYTHON||'python',['-B','-m','seremy.server','--port','0','--output',path.join(evidence,'publications')],
    {cwd:path.resolve(__dirname,'../..'),windowsHide:true,stdio:['ignore','pipe','pipe'],env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}});
  let logs='',browser;server.stderr.on('data',data=>{logs+=data;});
  const checks=[],cases=[],errors=[];
  try{
    const url=await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(new Error('Startup timeout '+logs)),15000);
      server.on('exit',code=>{clearTimeout(timer);reject(new Error('Server exit '+code+' '+logs));});
      server.stdout.on('data',data=>{const match=String(data).match(/http:\/\/127\.0\.0\.1:\d+/);if(match){clearTimeout(timer);resolve(match[0]);}});
    });
    browser=await chromium.launch(process.env.CHROME_BIN?{executablePath:process.env.CHROME_BIN}:{});
    const page=await browser.newPage({viewport:{width:1280,height:800}});page.on('pageerror',error=>errors.push(error.message));await page.goto(url);
    async function analyze(name){
      await page.locator('#connect').click();assert.match(await page.locator('#input-profile').innerText(),/JavaScript, JSX and TSX are excluded/);
      await page.locator('#value').fill(path.join(input,name));await page.locator('#start').click();
      await page.waitForFunction(()=>!document.querySelector('#start').disabled);
      assert.equal(await page.locator('#connect-dialog').isVisible(),false);
      const frame=page.frameLocator('#map');await frame.locator('#status').filter({hasText:/source verified|No embedded source/}).waitFor();
      await frame.locator('#show-coverage').click();assert.equal(await frame.locator('#coverage-tools').getAttribute('open'),'');
      const data=JSON.parse(await frame.locator('#fixture').textContent());
      const graph=await (await page.request.get(new URL(await page.locator('#download').getAttribute('href'),url).href)).json();
      assert.deepEqual(data.coverage,graph.contents.coverage);assert.deepEqual(data.analysis.exclusions,graph.contents.inventory.exclusions);
      assert.match(await frame.locator('#analysis-coverage').innerText(),new RegExp(graph.contents.profile));
      cases.push({name,coverage:data.coverage,profile:data.analysis.profile,source_files:Object.keys(data.files)});
      return {frame,data};
    }
    let {frame,data}=await analyze('unsupported');assert.equal(data.coverage.s02.source_file_count,0);
    assert.match(await page.locator('#status').innerText(),/No supported source/);
    assert.match(await frame.locator('#map-empty').innerText(),/No supported source files/);
    assert.equal(await frame.locator('#mini').isVisible(),false);assert.doesNotMatch(await frame.locator('#status').innerText(),/source verified/);
    await frame.getByText('Excluded entries and reasons',{exact:true}).click();
    assert.match(await frame.locator('#analysis-coverage').innerText(),/entry.js.*excluded_by_product_profile/);
    assert.match(await frame.locator('#analysis-coverage').innerText(),/view.tsx.*excluded_by_product_profile/);
    await page.screenshot({path:path.join(evidence,'unsupported-only.png')});
    checks.push('Unsupported-only JS/TSX input shows an explicit empty state, language scope and snapshot-matched exclusions');
    ({frame,data}=await analyze('limited'));assert.equal(data.coverage.s02.failed,2);assert.equal(data.coverage.s02.complete,1);assert.equal(data.coverage.s02.partial,1);
    assert.match(await page.locator('#status').innerText(),/parse limits/);assert.match(await page.locator('#summary').innerText(),/1 complete, 1 partial, 2 failed/);
    await frame.getByText('Parse limitations by file',{exact:true}).click();
    assert.match(await frame.locator('#analysis-coverage').innerText(),/broken.py.*failed/);assert.match(await frame.locator('#analysis-coverage').innerText(),/encoding.py.*failed/);
    assert.match(await frame.locator('#analysis-coverage').innerText(),/partial.ts.*partial/);
    assert.ok(data.outcomes.some(row=>row.outcome==='UNSUPPORTED'));
    await frame.getByText('Resolution outcome counts',{exact:true}).click();assert.equal(data.coverage.s03.outcome_counts.UNSUPPORTED,2);assert.match(await frame.locator('#analysis-coverage').innerText(),/UNSUPPORTED: 2/);
    await page.screenshot({path:path.join(evidence,'parse-limits.png')});
    checks.push('Partial TypeScript syntax, Python failure, invalid encoding and dynamic-target outcomes remain visible with exact file and outcome counts');
    ({frame,data}=await analyze('isolated'));assert.equal(data.edges.length,0);assert.equal(data.coverage.s02.complete,1);
    assert.equal(await frame.locator('#map-empty').count(),0);assert.equal(await frame.locator('.file').count(),1);
    assert.match(await frame.locator('#inspection-empty').innerText(),/No bound call relationships/);
    assert.match(await frame.locator('#analysis-coverage').innerText(),/Zero relationships do not establish/);
    checks.push('A parsed file without bound calls stays explorable and zero edges do not imply complete dependency analysis');
    const before={src:await page.locator('#map').getAttribute('src'),camera:await frame.locator('#world').getAttribute('transform'),repository:await page.locator('#connect').innerText(),graph:await page.locator('#download').getAttribute('href')};
    await page.locator('#connect').click();await page.locator('#value').fill(path.join(input,'missing'));await page.locator('#start').click();
    await page.waitForFunction(()=>!document.querySelector('#start').disabled);assert.equal(await page.locator('#connect-dialog').isVisible(),true);
    assert.ok((await page.locator('#connection-status').innerText()).length);await page.locator('#close-connect').click();
    assert.deepEqual({src:await page.locator('#map').getAttribute('src'),camera:await frame.locator('#world').getAttribute('transform'),repository:await page.locator('#connect').innerText(),graph:await page.locator('#download').getAttribute('href')},before);
    assert.equal(await page.evaluate(()=>repositoryName),'isolated');
    await page.route('**/architecture.md',route=>route.fulfill({status:404,body:'expired'}));await page.locator('#doc-tab').click();
    await page.locator('#status').filter({hasText:'unavailable or expired'}).waitFor();assert.equal(await page.locator('#map').isVisible(),true);await page.unroute('**/architecture.md');
    checks.push('Failed replacement and unavailable documentation preserve the current map and identify the recovery action');
    ({frame,data}=await analyze('unreadable'));assert.equal(data.coverage.s02.source_file_count,1);assert.equal(data.coverage.s02.failed,1);
    assert.match(await frame.locator('#map-empty').innerText(),/No displayable source/);assert.doesNotMatch(await frame.locator('#status').innerText(),/source verified/);
    checks.push('An encoding-only failure is distinguished from unsupported input and makes no source-verification claim');
    ({frame,data}=await analyze('skipped'));assert.equal(data.coverage.s02.source_file_count,1);assert.equal(data.coverage.s02.not_processed,1);assert.equal(data.coverage.s02.parsed_file_records,0);
    assert.equal(data.analysis.skipped_inputs[0].file_id,'oversized.py');assert.equal(data.analysis.skipped_inputs[0].bucket,'not_processed');
    await frame.getByText('Inputs not processed',{exact:true}).click();assert.match(await frame.locator('#analysis-coverage').innerText(),/oversized.py.*not_processed/);
    assert.ok((await frame.locator('#analysis-coverage').innerText()).includes(data.analysis.skipped_inputs[0].reason));
    assert.match(await frame.locator('#map-empty').innerText(),/No displayable source/);
    checks.push('A source input skipped at the byte limit exposes its exact filename and read-boundary reason without inventing parse records');
    ({frame,data}=await analyze('empty'));assert.equal(data.coverage.inventory.input_count,0);assert.match(await frame.locator('#map-empty').innerText(),/No supported source files/);
    await frame.locator('#fit').click();assert.doesNotMatch(await frame.locator('#world').getAttribute('transform'),/NaN|Infinity/);
    await frame.locator('#toggle-search').click();assert.equal(await frame.locator('#open').isDisabled(),true);
    checks.push('An empty directory has a stable camera, visible guidance and disabled empty Find action');
    assert.deepEqual(errors,[]);const result={status:'passed',browser:browser.version(),executable:process.env.CHROME_BIN||'playwright-chromium',checks,cases,page_errors:errors};
    fs.writeFileSync(path.join(evidence,'checks.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
  }finally{
    if(browser)await browser.close();server.kill();
    assert.equal(path.dirname(input),path.resolve(os.tmpdir()));assert.match(path.basename(input),/^seremy-coverage-/);fs.rmSync(input,{recursive:true,force:true});
  }
}
run().catch(error=>{console.error(error);process.exitCode=1;});
