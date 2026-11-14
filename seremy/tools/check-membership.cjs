// Inspect an actual opt-in membership publication in either source renderer.
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const {pathToFileURL,requireRenderer}=require('./map-test-url.cjs');

async function run(){
  const publication=path.resolve(process.argv[2]),evidence=path.resolve(process.argv[3]);fs.mkdirSync(evidence,{recursive:true});
  const graph=JSON.parse(fs.readFileSync(path.join(publication,'graph.json'),'utf8'));
  const membership=graph.contents.s05.artifact.experimental_membership.artifact;
  const browser=await chromium.launch(process.env.CHROME_BIN?{executablePath:process.env.CHROME_BIN}:{});
  const errors=[],checks=[];
  try{
    const page=await browser.newPage({viewport:{width:1440,height:900}});page.on('pageerror',error=>errors.push(error.message));
    await page.goto(pathToFileURL(path.join(publication,'map.html')).href);
    await page.locator('#status').filter({hasText:'source verified'}).waitFor();await requireRenderer(page);
    const fixture=await page.locator('#fixture').textContent(),data=JSON.parse(fixture);
    assert.deepEqual(data.analysis.membership,membership);
    assert.equal(data.edges.length,4);assert.equal(data.coverage.s03.direct_edge_count,3);
    await page.locator('#show-coverage').click();
    await page.getByText('Experimental membership coverage',{exact:true}).click();
    assert.match(await page.locator('#analysis-coverage').innerText(),/Experimental membership/);
    assert.match(await page.locator('#analysis-coverage').innerText(),/4\/7 assigned.*3 unassigned including 1 disputed/);
    assert.equal(membership.upstream_coverage.s02.failed,1);
    checks.push('Opt-in membership, disputes and failed source coverage are exported without changing the three observed calls or four source sites');
    const edge=data.edges.find(e=>e.from.file==='clients.py'&&e.to.file==='shared.py');
    await page.locator('#coverage-tools').evaluate(n=>n.open=false);
    await page.locator('#edges').selectOption(edge.id);await page.locator('#origin').click();
    const camera=await page.locator('#world').getAttribute('transform');
    await page.locator('#target').click();await page.locator('#detail').filter({hasText:'shared.py:1'}).waitFor();
    await page.locator('#back').click();assert.equal(await page.locator('#world').getAttribute('transform'),camera);
    await page.locator('#arrangement-tools').evaluate(n=>n.open=true);await page.locator('#save-view').click();
    await page.reload();await page.locator('#status').filter({hasText:'source verified'}).waitFor();
    await page.locator('#inspect').click();await page.locator('#arrangement-tools').evaluate(n=>n.open=true);await page.locator('#restore-view').click();
    assert.equal(await page.locator('#fixture').textContent(),fixture);
    checks.push('Call navigation, Back and saved-view restoration preserve source evidence and membership lineage');
    await page.locator('#show-coverage').click();await page.screenshot({path:path.join(evidence,'membership.png')});
    assert.deepEqual(errors,[]);
    const result={status:'passed',browser:browser.version(),renderer:process.env.SEREMY_RENDERER||'svg',graph_digest:data.bundle.content_digest,
      membership_version:membership.views[0].version,checks,page_errors:errors};
    fs.writeFileSync(path.join(evidence,'checks.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
  }finally{await browser.close();}
}
run().catch(error=>{console.error(error);process.exitCode=1;});
