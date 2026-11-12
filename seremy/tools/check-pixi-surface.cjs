// Verify actual GPU paint, saved renderer state and real WebGL failure recovery.
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');

async function run(){
  const root=path.resolve(process.argv[2]),evidence=path.resolve(process.argv[3]);
  fs.mkdirSync(evidence,{recursive:true});
  const url=pathToFileURL(path.join(root,'map.html'));url.searchParams.set('renderer','pixi');
  const browser=await chromium.launch({args:['--use-angle=d3d11','--enable-webgl','--ignore-gpu-blocklist']});
  const checks=[],errors=[];let gpu;
  async function open(browser,url){
    const page=await browser.newPage({viewport:{width:1440,height:900}});
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(url.href);await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('source verified'));
    return page;
  }
  try{
    const page=await open(browser,url);
    gpu=await page.evaluate(()=>window.__seremyRendererInfo());
    assert.equal(gpu.engine,'pixi');assert.ok(gpu.objects>0&&gpu.text_objects>0);assert.equal(gpu.gl_error,0);
    // Read pixels immediately after a synchronous controller draw, before the drawing buffer is cleared.
    const pixels=await page.evaluate(()=>{
      document.querySelector('#in').click();
      const canvas=document.querySelector('#pixi-surface'),gl=canvas.getContext('webgl2'),data=new Uint8Array(canvas.width*canvas.height*4);
      gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,data);
      let painted=0;for(let i=3;i<data.length;i+=4)if(data[i])painted++;
      return {painted,error:gl.getError(),hidden:getComputedStyle(document.querySelector('#world')).opacity};
    });
    assert.equal(pixels.error,0);assert.ok(pixels.painted>1000);assert.equal(pixels.hidden,'0');
    checks.push('WebGL paints nontransparent scene pixels while the semantic SVG layer is visually hidden');
    await page.locator('#inspect').click();await page.locator('#arrangement-tools summary').click();
    const before=await page.locator('#world').getAttribute('transform');
    await page.locator('#renderer').selectOption('svg');assert.equal(await page.evaluate(()=>window.__seremyRendererInfo().engine),'svg');
    assert.equal(await page.locator('#pixi-surface').isVisible(),false);
    await page.locator('#renderer').selectOption('pixi');await page.locator('body[data-renderer=pixi]').waitFor();
    assert.equal(await page.locator('#world').getAttribute('transform'),before);
    checks.push('Switching renderers preserves the existing scene and camera');
    await page.locator('#save-view').click();await page.reload();
    await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('source verified'));
    await page.locator('#inspect').click();await page.locator('#arrangement-tools summary').click();
    await page.locator('#renderer').selectOption('svg');await page.locator('#restore-view').click();
    await page.locator('body[data-renderer=pixi]').waitFor();
    assert.equal(await page.locator('#world').getAttribute('transform'),before);
    checks.push('Saved views restore the renderer and camera after reload');
    await page.screenshot({path:path.join(evidence,'integrated-pixi.png')});
    await page.evaluate(()=>document.querySelector('#pixi-surface').getContext('webgl2').getExtension('WEBGL_lose_context').loseContext());
    await page.locator('body[data-renderer=svg]').waitFor();assert.match(await page.locator('#renderer-status').textContent(),/context lost/);
    await page.locator('#fit').click();assert.ok(await page.locator('.file').count());
    checks.push('A real lost WebGL context falls back to usable SVG without losing evidence');
    await page.close();
  }finally{await browser.close();}
  const unavailable=await chromium.launch({args:['--disable-webgl']});
  try{
    const page=await open(unavailable,url);
    assert.equal(await page.evaluate(()=>window.__seremyRendererInfo().engine),'svg');
    assert.match(await page.locator('#renderer-status').textContent(),/unavailable/);
    await page.locator('#inspect').click();
    const edge=await page.evaluate(()=>JSON.parse(document.querySelector('#fixture').textContent).edges.find(edge=>edge.to));
    await page.locator('#edges').selectOption(edge.id);await page.locator('#origin').click();
    assert.ok(await page.locator('.source-focus').count());await page.locator('#target').click();
    assert.ok(await page.locator('.source-focus').count());
    checks.push('Unavailable WebGL falls back to SVG with working source and target navigation');
    await page.close();
    const missingRuntime=path.join(evidence,'without-runtime.html');
    fs.writeFileSync(missingRuntime,fs.readFileSync(path.join(root,'map.html'),'utf8').replace(/(<script id="pixi-runtime" type="text\/plain">)[\s\S]*?(<\/script>)/,'$1$2'));
    const offline=await open(unavailable,pathToFileURL(missingRuntime));
    assert.equal(await offline.locator('#renderer option[value=pixi]').isDisabled(),true);
    assert.equal(await offline.evaluate(()=>window.__seremyRendererInfo().engine),'svg');
    await offline.locator('#fit').click();assert.ok(await offline.locator('.file').count());
    checks.push('A Python-only export without the optional Pixi runtime remains usable in SVG');
  }finally{await unavailable.close();}
  assert.deepEqual(errors,[]);
  const report={status:'passed',gpu,checks,page_errors:errors};
  fs.writeFileSync(path.join(evidence,'checks.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
}
run().catch(error=>{console.error(error);process.exitCode=1;});
