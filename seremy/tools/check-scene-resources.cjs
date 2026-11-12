const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');

// Observe actual WebGL allocation/deletion calls, independently of Pixi internals.
function observeTextures(){
  const contexts=new Map();
  function context(gl){if(!contexts.has(gl))contexts.set(gl,{unit:0,bindings:new Map(),textures:new Map(),created:0,deleted:0,uploads:0,peak:0});return contexts.get(gl);}
  function bytes(state){return [...state.textures.values()].reduce((sum,texture)=>sum+[...texture.levels.values()].reduce((n,level)=>n+level,0),0);}
  for(const api of [WebGLRenderingContext,WebGL2RenderingContext])for(const name of ['activeTexture','createTexture','bindTexture','texImage2D','texStorage2D','deleteTexture']){
    const prototype=api.prototype;if(!Object.hasOwn(prototype,name))continue;
    const original=prototype[name];prototype[name]=function(...args){
      const state=context(this),result=original.apply(this,args),key=state.unit+'|'+args[0];
      if(name==='activeTexture')state.unit=args[0];
      if(name==='createTexture'){state.created++;state.textures.set(result,{levels:new Map()});}
      if(name==='bindTexture')state.bindings.set(key,args[1]);
      if(name==='deleteTexture'){state.deleted++;state.textures.delete(args[0]);}
      if(name==='texImage2D'||name==='texStorage2D'){
        const texture=state.textures.get(state.bindings.get(key));
        if(texture){
          const format=args[2],rgba=[this.RGBA,this.RGBA8,this.SRGB8_ALPHA8].includes(format);
          if(rgba){
            if(name==='texStorage2D')for(let level=0;level<args[1];level++)texture.levels.set(level,Math.max(1,args[3]>>level)*Math.max(1,args[4]>>level)*4);
            else {const source=args[5],width=args.length>=9?args[3]:source?.videoWidth||source?.naturalWidth||source?.width||0,height=args.length>=9?args[4]:source?.videoHeight||source?.naturalHeight||source?.height||0;texture.levels.set(args[1],width*height*4);}
          }
          state.uploads++;state.peak=Math.max(state.peak,bytes(state));
        }
      }
      return result;
    };
  }
  window.__textureStats=()=>{
    const rows=[...contexts].filter(([gl])=>gl.canvas.id==='pixi-surface').map(([,state])=>({created:state.created,deleted:state.deleted,live:state.textures.size,uploads:state.uploads,rgba8_estimated_bytes:bytes(state),peak_rgba8_estimated_bytes:state.peak}));
    return rows.reduce((total,row)=>{for(const [key,value] of Object.entries(row))total[key]=(total[key]||0)+value;return total;},{});
  };
}
async function run(){
  const publication=path.resolve(process.argv[2]),evidence=path.resolve(process.argv[3]);fs.mkdirSync(evidence,{recursive:true});
  const browser=await chromium.launch({args:['--use-angle=d3d11','--enable-webgl','--ignore-gpu-blocklist']});
  const checks=[],errors=[],samples=[];
  try{
    const page=await browser.newPage({viewport:{width:1440,height:900}});await page.addInitScript(observeTextures);
    page.on('pageerror',error=>errors.push(error.message));
    const url=pathToFileURL(path.join(publication,'map.html'));url.searchParams.set('renderer','pixi');await page.goto(url.href);
    await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('source verified'));
    async function sample(label){const value=await page.evaluate(()=>({renderer:window.__seremyRendererInfo(),textures:window.__textureStats()}));assert.equal(value.renderer.gl_error,0);samples.push({label,...value});return value;}
    await page.locator('#fit').click();const before=await sample('overview');assert.equal(before.renderer.engine,'pixi');
    const file=await page.locator('.file').first().elementHandle();
    await page.evaluate(()=>{const map=document.querySelector('#map'),b=map.getBoundingClientRect();for(let i=0;i<10;i++)map.dispatchEvent(new WheelEvent('wheel',{deltaY:i%2?1:-1,clientX:b.x+b.width/2,clientY:b.y+b.height/2,bubbles:true,cancelable:true}));});
    const after=await sample('overview-after-camera-updates');
    assert.equal(after.renderer.created,before.renderer.created);assert.equal(after.renderer.text_updates,before.renderer.text_updates);
    assert.equal(after.renderer.scene.created,before.renderer.scene.created);assert.equal(after.textures.uploads,before.textures.uploads);
    assert.equal(await file.evaluate(node=>node.isConnected),true);
    checks.push('Real overview zoom reuses semantic nodes, GPU objects, text styles and uploaded textures');
    await page.locator('#inspect').click();const data=JSON.parse(await page.locator('#fixture').textContent());
    const edge=data.edges.find(edge=>edge.from.file==='src/utils/isAction.ts'&&edge.to.file==='src/utils/isPlainObject.ts')||data.edges[0];
    await page.locator('#edges').selectOption(edge.id);await page.locator('#origin').click();
    const source=await sample('source');assert.ok(source.textures.rgba8_estimated_bytes>0);
    const token=page.locator('.token[data-file="'+edge.from.file+'"][data-start="'+edge.from.start+'"]');await token.focus();await token.press('Enter');
    await page.locator('#target').click();await page.locator('#back').click();assert.equal(await page.locator('#edges').inputValue(),edge.id);
    checks.push('Keyboard source focus, target and Back preserve the selected byte-range evidence');
    // Evict all visible files while leaving folder headings alive.
    const bounds=await page.locator('#map').boundingBox();await page.mouse.move(bounds.x+bounds.width*.4,bounds.y+20);await page.mouse.down();
    await page.mouse.move(bounds.x+bounds.width*.4+30,bounds.y+40);
    await page.mouse.move(bounds.x+200000,bounds.y+200000);await page.mouse.up();
    const evicted=await sample('offscreen');assert.ok(evicted.renderer.destroyed>source.renderer.destroyed);
    fs.writeFileSync(path.join(evidence,'allocation-samples.json'),JSON.stringify(samples,null,2));
    assert.ok(evicted.textures.deleted>source.textures.deleted);assert.ok(evicted.textures.rgba8_estimated_bytes<source.textures.rgba8_estimated_bytes);
    checks.push('Viewport eviction destroys old GPU objects and releases idle GL text allocations');
    await page.locator('#fit').click();await page.locator('#arrangement-tools summary').click();await page.locator('#renderer').selectOption('svg');
    const released=await page.evaluate(()=>window.__textureStats());samples.push({label:'svg-release',textures:released});
    assert.ok(released.rgba8_estimated_bytes<source.textures.rgba8_estimated_bytes);
    await page.locator('#renderer').selectOption('pixi');await page.locator('body[data-renderer=pixi]').waitFor();
    const restored=await sample('pixi-restored');assert.ok(restored.renderer.objects>0);
    checks.push('Switching to SVG releases GPU scene/text resources and Pixi can rebuild the same map');
    await page.screenshot({path:path.join(evidence,'source-resources.png')});assert.deepEqual(errors,[]);
    const result={status:'passed',browser:browser.version(),checks,samples,page_errors:errors,scope:'Instrumented WebGL texture allocation/delete calls. RGBA8 level storage estimate excludes driver overhead, buffers, non-RGBA8 formats and the framebuffer; not total VRAM. Instrumentation is separate from timing benchmarks.'};
    fs.writeFileSync(path.join(evidence,'checks.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
  }finally{await browser.close();}
}
run().catch(error=>{console.error(error);process.exitCode=1;});
