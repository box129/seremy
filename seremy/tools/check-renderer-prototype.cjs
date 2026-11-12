const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');

async function run(){
  const [publication,prototype,evidence]=process.argv.slice(2,5).map(value=>path.resolve(value));
  const dpr=Number(process.argv[5]||1);
  fs.mkdirSync(evidence,{recursive:true});
  const browser=await chromium.launch({...process.env.CHROME_BIN?{executablePath:process.env.CHROME_BIN}:{},args:['--use-angle=d3d11','--enable-webgl','--ignore-gpu-blocklist']});
  const checks=[],errors=[];
  try{
    const svg=await browser.newPage({viewport:{width:1440,height:900},deviceScaleFactor:dpr});
    await svg.goto(pathToFileURL(path.join(publication,'map.html')).href);
    await svg.waitForFunction(()=>document.querySelector('#status').textContent.includes('source verified'));
    const expected=await svg.locator('.file').evaluateAll(nodes=>Object.fromEntries(nodes.map(node=>[node.dataset.file,['x','y','width','height'].map(key=>Number(node.getAttribute(key)))])));
    await svg.addStyleTag({content:'#map{height:800px!important}'});
    const page=await browser.newPage({viewport:{width:1440,height:900},deviceScaleFactor:dpr});
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(pathToFileURL(prototype).href);
    await page.waitForFunction(()=>window.__rendererExperiment,{},{timeout:60000});
    await page.evaluate(()=>window.__rendererExperiment.resize(1440,800));
    assert.deepEqual(await page.evaluate(()=>window.__rendererExperiment.geometry()),expected);
    const fixture=JSON.parse(await page.locator('#fixture').textContent());
    const edge=fixture.edges.find(edge=>edge.from.file==='src/utils/isAction.ts'&&edge.to.file==='src/utils/isPlainObject.ts')||fixture.edges[0];
    await page.locator('#edges').selectOption(edge.id);await page.locator('#origin').click();
    const point=await page.evaluate(id=>window.__rendererExperiment.tokenPoint(id),edge.id);
    await page.mouse.click(point.x,point.y);
    const origin=await page.evaluate(()=>window.__rendererExperiment.state());
    assert.equal(origin.selected,edge.id);assert.deepEqual(origin.focus,edge.from);
    await svg.locator('#inspect').click();await svg.locator('#edges').selectOption(edge.id);await svg.locator('#origin').click();
    await svg.locator('#close-files').click();await svg.locator('#close-inspector').click();
    const svgCamera=await svg.locator('#world').evaluate(node=>{const [x,y,k]=node.getAttribute('transform').match(/-?\d+(?:\.\d+)?(?:e[+-]?\d+)?/gi).map(Number);return {x,y,k};});
    assert.deepEqual(origin.camera,svgCamera);
    await svg.screenshot({path:path.join(evidence,'svg-source.png')});
    await page.screenshot({path:path.join(evidence,'pixi-source.png')});
    await page.locator('#target').click();
    assert.deepEqual((await page.evaluate(()=>window.__rendererExperiment.state())).focus,edge.to);
    await page.locator('#back').click();assert.deepEqual(await page.evaluate(()=>window.__rendererExperiment.state()),origin);
    checks.push('Pixi consumes identical layout geometry, hits the actual source range, follows its bound target and restores selection and camera with Back');
    await page.locator('#collapse').click();
    const collapsed=await page.evaluate(()=>window.__rendererExperiment.state());
    assert.ok(collapsed.closed.length>0);
    await page.locator('#target').click();await page.locator('#back').click();
    assert.deepEqual(await page.evaluate(()=>window.__rendererExperiment.state()),collapsed);
    await page.locator('#collapse').click();await page.locator('#fit').click();
    await page.screenshot({path:path.join(evidence,'pixi-overview.png')});
    checks.push('Collapsed groups retain navigation and restore their state after following and returning');
    const gpu=await page.evaluate(()=>window.__rendererExperiment.gpu);
    assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(evidence,'checks.json'),JSON.stringify({status:'passed',checks,gpu,dpr,canvas:[1440,800],page_errors:errors},null,2)+'\n');
    console.log(JSON.stringify({status:'passed',checks,gpu}));
  }finally{await browser.close();}
}
run().catch(error=>{console.error(error);process.exitCode=1;});
