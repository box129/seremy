// Native UI journeys across repository sizes, desktop viewports and high DPI.
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');

async function state(page){return page.evaluate(()=>({camera:document.querySelector('#world').getAttribute('transform'),edge:document.querySelector('#edges').value,
  focus:[...document.querySelectorAll('.source-focus')].map(node=>[node.dataset.file,node.dataset.start,node.dataset.end,node.dataset.line]),
  tree:[...document.querySelectorAll('#tree details[open]')].map(node=>node.dataset.directory),scroll:document.querySelector('#repository').scrollTop}));}
async function run(){
  const [redux,prepared,evidence]=process.argv.slice(2).map(value=>path.resolve(value));
  const inputs=JSON.parse(fs.readFileSync(path.join(prepared,'inputs.json'),'utf8'));
  fs.mkdirSync(evidence,{recursive:true});
  const browser=await chromium.launch({...process.env.CHROME_BIN?{executablePath:process.env.CHROME_BIN}:{},args:['--use-angle=d3d11','--enable-webgl','--ignore-gpu-blocklist']});
  const checks=[],screens=[],errors=[];
  try{
    for(const [name,publication] of [['redux',redux],['synthetic',inputs.synthetic.publication],['pydantic',inputs.pydantic.publication]]){
      for(const config of [{width:1440,height:900,dpr:1},{width:1280,height:800,dpr:1},{width:1440,height:900,dpr:2}]){
        const context=await browser.newContext({viewport:{width:config.width,height:config.height},deviceScaleFactor:config.dpr});
        const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
        await page.goto(pathToFileURL(path.join(publication,'map.html')).href,{timeout:120000});
        await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('source verified'),{},{timeout:120000});
        const data=JSON.parse(await page.locator('#fixture').textContent());
        const edge=name==='redux'?data.edges.find(edge=>edge.from.file==='src/utils/isAction.ts'&&edge.to.file==='src/utils/isPlainObject.ts'):data.edges[0];
        await page.locator('#inspect').click();await page.locator('#edges').selectOption(edge.id);await page.locator('#origin').press('Enter');
        const token=page.locator('.token[data-file="'+edge.from.file+'"][data-start="'+edge.from.start+'"]');
        await token.click();
        const origin=await state(page);
        assert.equal(origin.edge,edge.id);
        await page.locator('#target').press('Enter');
        assert.equal((await state(page)).focus[0][0],edge.to.file);
        await page.locator('#back').press('Enter');assert.deepEqual(await state(page),origin);
        await page.locator('#close-files').press('Enter');await page.locator('#close-inspector').press('Enter');
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth||document.documentElement.scrollHeight>innerHeight),false);
        const filename=name+'-'+config.width+'x'+config.height+'-dpr'+config.dpr+'.png';
        await page.screenshot({path:path.join(evidence,filename)});screens.push({name,...config,file:filename});
        await page.locator('#collapse').click();await page.locator('#fit').click();
        await page.locator('#inspect').click();
        const closed=await state(page);
        await page.locator('#target').press('Enter');await page.locator('#back').press('Enter');assert.deepEqual(await state(page),closed);
        await page.locator('#collapse').click();await page.locator('#fit').click();
        checks.push(name+' source → target → Back → collapse → follow → Back at '+config.width+'×'+config.height+' DPR '+config.dpr);
        await context.close();
      }
    }
    // Capture the same named source file and viewport as the historical CodeCanvas image.
    const page=await browser.newPage({viewport:{width:1225,height:580}});
    await page.goto(pathToFileURL(path.join(redux,'map.html')).href);
    await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('source verified'));
    await page.locator('#close-files').click();await page.locator('#files').selectOption('src/utils/formatProdErrorMessage.ts');await page.locator('#open').click();
    const card=page.locator('.file[data-file="src/utils/formatProdErrorMessage.ts"]');
    const bounds=await card.boundingBox(),map=await page.locator('#map').boundingBox();
    // Keep readable source at the product's minimum source-detail scale.
    await page.mouse.move(map.x+map.width/2,map.y+map.height/2);await page.mouse.wheel(0,Math.log(1.25/.51)/.002);
    await page.waitForFunction(()=>Number(document.querySelector('#world').getAttribute('transform').match(/scale\(([^)]+)\)/)[1])<.6);
    const after=await card.boundingBox(),dx=474-(after.x+after.width/2),dy=270-(after.y+after.height/2);
    await page.mouse.move(map.x+map.width/2,map.y+map.height/2);await page.mouse.down();
    await page.mouse.move(map.x+map.width/2+dx,map.y+map.height/2+dy,{steps:5});await page.mouse.up();
    await page.screenshot({path:path.join(evidence,'seremy-reference-source.png')});
    assert.ok(bounds.width>0);assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(evidence,'workflow-checks.json'),JSON.stringify({status:'passed',browser:browser.version(),checks,screens,page_errors:errors,
      reference:{viewport:[1225,580],file:'src/utils/formatProdErrorMessage.ts',source_zoom:.51,limits:'Historical CodeCanvas revision and camera transform are unavailable. Source text and viewport are aligned; source-card width and zoom policy differ.'}},null,2)+'\n');
    console.log(JSON.stringify({status:'passed',checks}));
  }finally{await browser.close();}
}
run().catch(error=>{console.error(error);process.exitCode=1;});
