// Exercise filters and exact source regions using a real analyzed repository.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {spawnSync}=require('node:child_process');
const {pathToFileURL,requireRenderer}=require('./map-test-url.cjs');

async function run(){
  const evidence=path.resolve(process.argv[2]);
  fs.mkdirSync(evidence,{recursive:true});
  const input=fs.mkdtempSync(path.join(os.tmpdir(),'seremy-connections-'));
  let publication;
  try{
    fs.writeFileSync(path.join(input,'entry.py'),[
      '# é 🦊', 'import math', 'from target import chosen', '', 'def outer():',
      '\tlabel = "é🦊"; chosen(); chosen()', '\tdef inner():', '\t\treturn chosen()',
      '\treturn missing()', ''
    ].join('\r\n'));
    fs.writeFileSync(path.join(input,'target.py'),'def chosen():\n    return 1\n');
    fs.writeFileSync(path.join(input,'external.ts'),"import thing from 'external-lib';\nexport function member(x: any) { thing(); return x.run(); }\n");
    const result=spawnSync(process.env.PYTHON||'python',['-B','-m','seremy','analyze',input,'--output',path.join(evidence,'publication')],
      {cwd:path.resolve(__dirname,'../..'),windowsHide:true,encoding:'utf8',timeout:60000});
    assert.equal(result.status,0,result.stderr);
    publication=JSON.parse(result.stdout);
  }finally{fs.rmSync(input,{recursive:true,force:true});}
  const browser=await chromium.launch(process.env.CHROME_BIN?{executablePath:process.env.CHROME_BIN}:{});
  const checks=[],errors=[];
  try{
    const page=await browser.newPage({viewport:{width:1440,height:900}});
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(pathToFileURL(publication.map).href);
    await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('source verified'));
    await requireRenderer(page);
    const data=JSON.parse(await page.locator('#fixture').textContent());
    assert.equal(data.edges.length,3);
    assert.equal(new Set(data.edges.map(edge=>edge.relation_id)).size,2);
    await page.locator('#inspect').click();
    assert.match(await page.locator('#connection-count').textContent(),/^2 relationships · 3 source sites$/);
    await page.locator('#files').selectOption('entry.py');
    await page.locator('#open').click();
    await page.locator('#connection-mode').selectOption('outgoing');
    assert.equal(await page.locator('#scope-label').textContent(),'entry.py');
    assert.equal(await page.locator('#edges option').count(),4);
    await page.locator('#connection-mode').selectOption('incoming');
    assert.equal(await page.locator('.wire').count(),0);
    assert.equal(await page.locator('#edges option').count(),1);
    assert.match(await page.locator('#connection-count').textContent(),/^0 relationships · 0 source sites$/);
    await page.locator('#back').click();
    assert.equal(await page.locator('#connection-mode').inputValue(),'outgoing');
    await page.locator('#files').selectOption('target.py');
    await page.locator('#open').click();
    await page.locator('#connection-mode').selectOption('incoming');
    assert.match(await page.locator('#connection-count').textContent(),/^2 relationships · 3 source sites$/);
    const edge=[...data.edges].sort((a,b)=>a.from.start-b.from.start)[0];
    await page.locator('#edges').selectOption(edge.id);
    assert.equal(await page.locator('#scope-label').textContent(),'target.py');
    await page.locator('#connection-mode').selectOption('neighborhood');
    assert.equal(await page.locator('#edges option').count(),4);
    const origin=await page.locator('#world').getAttribute('transform');
    await page.locator('#target').click();
    await page.locator('#back').click();
    assert.equal(await page.locator('#world').getAttribute('transform'),origin);
    assert.equal(await page.locator('#scope-label').textContent(),'target.py');
    assert.equal(await page.locator('#connection-mode').inputValue(),'neighborhood');
    assert.ok(await page.locator('.wire[marker-end="url(#direction)"]').count()>0);
    checks.push('Direction filters, empty results, relationship/site counts, arrowheads and Back use the selected file scope');

    await page.locator('#connection-mode').selectOption('all');
    await page.locator('#edges').selectOption(edge.id);
    await page.locator('#origin').click();
    await page.locator('#close-files').click();
    const alignment=await page.evaluate(span=>{
      const data=JSON.parse(document.querySelector('#fixture').textContent);
      const prefix=new TextDecoder().decode(new TextEncoder().encode(data.files[span.file]).slice(0,span.start));
      const parts=prefix.split(/\r\n|\n/);
      const row=[...document.querySelectorAll('.code[data-file]')].find(node=>node.dataset.file===span.file&&Number(node.dataset.line)===parts.length);
      const text=row.querySelector('tspan[x]');
      const point=text.getStartPositionOfChar(parts.at(-1).replace(/\t/g,'    ').length);
      return Math.abs(Number(document.querySelector('.source-focus').getAttribute('x'))-point.x);
    },edge.from);
    assert.ok(alignment<1,'UTF-8 evidence must align with the rendered call after tabs and emoji');
    await page.locator('#region-tools summary').click();
    const entity=data.entities.find(entity=>entity.name==='outer');
    await page.locator('#regions').selectOption(entity.entity_id);
    const ranges=await page.locator('.source-focus').evaluateAll(nodes=>nodes.map(node=>[Number(node.dataset.start),Number(node.dataset.end)]));
    assert.ok(ranges.length>1);
    assert.ok(ranges.every(range=>range[0]===entity.decl_span[0]&&range[1]===entity.decl_span[1]));
    await page.locator('#back').click();
    assert.equal(await page.locator('#edges').inputValue(),edge.id);
    const nested=data.entities.find(entity=>entity.name==='inner');
    const nestedCall=data.edges.find(edge=>edge.from.start>nested.decl_span[0]&&edge.from.end<nested.decl_span[1]);
    await page.locator('#edges').selectOption(nestedCall.id);
    await page.locator('#origin').click();
    const regionIds=await page.locator('#regions option').evaluateAll(nodes=>nodes.map(node=>node.value));
    assert.deepEqual(regionIds.slice(1),[nested.entity_id,entity.entity_id]);
    assert.ok(await page.locator('tspan.string').count()>0);
    checks.push('Unicode, CRLF and tab offsets align with source; nested parser regions highlight exact byte ranges and restore with Back');

    await page.locator('#outcome-tools summary').click();
    const outcome=data.outcomes.find(record=>record.outcome==='MISSING'||record.outcome==='UNSUPPORTED');
    assert.ok(outcome);
    await page.locator('#outcomes').selectOption(outcome.candidate_id);
    assert.ok((await page.locator('#outcome-detail').textContent()).includes(outcome.reason));
    assert.equal(await page.locator('#target').isDisabled(),true);
    await page.locator('#origin').click();
    assert.equal(await page.locator('#outcomes').inputValue(),outcome.candidate_id);
    assert.ok(await page.locator('.source-focus').count()>0);
    const external=data.outcomes.find(record=>record.outcome==='EXTERNAL');
    assert.ok(external);
    await page.locator('#outcomes').selectOption(external.candidate_id);
    assert.match(await page.locator('#outcome-detail').textContent(),/EXTERNAL/);
    assert.equal(await page.locator('#target').isDisabled(),true);
    await page.screenshot({path:path.join(evidence,'outcomes.png')});
    checks.push('Missing or unsupported calls and external imports expose recorded reasons and retain source navigation without a target');
    await page.locator('#edges').selectOption(edge.id);
    await page.locator('#origin').click();
    await page.screenshot({path:path.join(evidence,'connections.png')});
    const tampered=path.join(evidence,'stale.html');
    fs.writeFileSync(tampered,fs.readFileSync(publication.map,'utf8').replace('# é 🦊','# changed'));
    await page.goto(pathToFileURL(tampered).href);
    await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('STALE'));
    await page.locator('#inspect').click();
    await page.locator('#outcome-tools summary').click();
    await page.locator('#outcomes').selectOption(outcome.candidate_id);
    assert.match(await page.locator('#outcome-detail').textContent(),/verification.*failed/);
    assert.equal(await page.locator('#origin').isDisabled(),true);
    assert.equal(await page.locator('#target').isDisabled(),true);
    checks.push('Stale embedded sources expose verification failure and disable all evidence navigation');
    assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(evidence,'checks.json'),JSON.stringify({status:'passed',checks,page_errors:errors},null,2)+'\n');
    console.log(JSON.stringify({status:'passed',checks}));
  }finally{await browser.close();}
}
run().catch(error=>{console.error(error);process.exitCode=1;});
