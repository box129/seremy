// Paired renderer measurements with identical source data, geometry, camera and canvas size.
const {chromium}=require('playwright');
const {execFileSync}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');

function percentile(values,fraction){const sorted=[...values].sort((a,b)=>a-b);return Number(sorted[Math.ceil(sorted.length*fraction)-1].toFixed(2));}
async function profile(page){
  return page.evaluate(async()=>{
    const map=document.querySelector('#map'),bounds=map.getBoundingClientRect(),samples=[];
    const frame=()=>new Promise(resolve=>requestAnimationFrame(resolve));
    let previous=await frame();
    for(let i=0;i<20;i++){
      const start=performance.now();
      map.dispatchEvent(new WheelEvent('wheel',{deltaY:i%2?60:-60,clientX:bounds.x+bounds.width/2,clientY:bounds.y+bounds.height/2,bubbles:true,cancelable:true}));
      const handler=performance.now()-start,first=await frame(),second=await frame();
      samples.push({handler_ms:handler,interaction_frame_interval_ms:first-previous,two_frame_ms:performance.now()-start});previous=second;
    }
    return samples;
  });
}
async function camera(page,renderer){
  return page.evaluate(renderer=>{
    if(renderer==='pixi')return window.__rendererExperiment.state().camera;
    const [x,y,k]=document.querySelector('#world').getAttribute('transform').match(/-?\d+(?:\.\d+)?(?:e[+-]?\d+)?/gi).map(Number);
    if(![x,y,k].every(Number.isFinite))throw new Error('Invalid measured camera');return {x,y,k};
  },renderer);
}
async function run(){
  const [redux,prepared,evidence]=process.argv.slice(2).map(value=>path.resolve(value));
  fs.mkdirSync(evidence,{recursive:true});
  const inputs=JSON.parse(fs.readFileSync(path.join(prepared,'inputs.json'),'utf8'));
  const cases=[['redux',redux],['synthetic',inputs.synthetic.publication],['pydantic',inputs.pydantic.publication]];
  const browser=await chromium.launch({...process.env.CHROME_BIN?{executablePath:process.env.CHROME_BIN}:{},args:['--use-angle=d3d11','--enable-webgl','--ignore-gpu-blocklist','--enable-precise-memory-info']});
  const results=[];let gpu=null;
  try{
    for(const [name,publication] of cases){
      const pixi=path.join(evidence,name+'-pixi.html');
      execFileSync(process.env.PYTHON||'python',['-B',path.join(__dirname,'build_renderer_prototype.py'),publication,pixi],{windowsHide:true});
      const svg=path.join(publication,'map.html');
      assert.ok(fs.readFileSync(svg,'utf8').includes('const measuredWidths=new Map()'),'Regenerate the map before measuring the width-cache change');
      const fixture=JSON.parse(fs.readFileSync(svg,'utf8').match(/<script id="fixture" type="application\/json">([\s\S]*?)<\/script>/)[1]);
      const edge=name==='redux'?fixture.edges.find(edge=>edge.from.file==='src/utils/isAction.ts'&&edge.to.file==='src/utils/isPlainObject.ts'):
        fixture.edges.find(edge=>new TextDecoder().decode(new TextEncoder().encode(fixture.files[edge.from.file]).slice(0,edge.from.start)).split('\n').length>80)||fixture.edges[0];
      const inventory={files:Object.keys(fixture.files).length,lines:Object.values(fixture.files).reduce((sum,text)=>sum+text.split('\n').length,0),source_sites:fixture.edges.length,digest:fixture.bundle.content_digest};
      let overviewCamera=null,sourceCamera=null;
      for(let trial=0;trial<3;trial++)for(const renderer of trial%2?['pixi','svg']:['svg','pixi']){
        const context=await browser.newContext({viewport:{width:1440,height:900},deviceScaleFactor:1});
        const page=await context.newPage(),errors=[];
        page.on('pageerror',error=>errors.push(error.message));
        const start=Date.now();await page.goto(pathToFileURL(renderer==='svg'?svg:pixi).href,{timeout:120000});
        await page.waitForFunction(renderer=>renderer==='pixi'?!!window.__rendererExperiment:document.querySelector('#status').textContent.includes('source verified'),renderer,{timeout:120000});
        const ready=Date.now()-start;
        if(renderer==='pixi'){
          gpu=await page.evaluate(()=>window.__rendererExperiment.gpu);
          await page.evaluate(()=>window.__rendererExperiment.resize(1440,800));
        }else{
          await page.addStyleTag({content:'#map{height:800px!important}'});
          await page.locator('#close-files').click();await page.locator('#fit').click();
        }
        await page.locator('#fit').click();
        if(!overviewCamera)overviewCamera=await camera(page,renderer);
        if(renderer==='pixi')await page.evaluate(value=>window.__rendererExperiment.setCamera(value),overviewCamera);
        else assert.deepEqual(await camera(page,renderer),overviewCamera);
        assert.deepEqual(await page.locator('#map').evaluate(node=>[node.clientWidth,node.clientHeight]),[1440,800]);
        const overview=await profile(page);
        if(renderer==='svg')await page.locator('#inspect').click();
        await page.locator('#edges').selectOption(edge.id);await page.locator('#origin').click();
        if(renderer==='svg')await page.locator('#close-inspector').click();
        if(!sourceCamera)sourceCamera=await camera(page,renderer);
        if(renderer==='pixi')await page.evaluate(value=>window.__rendererExperiment.setCamera(value),sourceCamera);
        else assert.deepEqual(await camera(page,renderer),sourceCamera);
        const source=await profile(page);
        const selection=await page.evaluate(async ids=>{
          const picker=document.querySelector('#edges'),values=[];
          for(let i=0;i<20;i++){
            const start=performance.now();picker.value=ids[i%ids.length];picker.dispatchEvent(new Event('change'));
            const handler=performance.now()-start;
            await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
            values.push({handler_ms:handler,two_frame_ms:performance.now()-start});
          }
          return values;
        },[edge.id,fixture.edges.at(-1).id]);
        const memory=await page.evaluate(()=>({js_heap_bytes:performance.memory?.usedJSHeapSize??null,
          dom_nodes:document.querySelectorAll('*').length,pixi_objects:window.__rendererExperiment?.state().objects??null}));
        if(trial===0)await page.screenshot({path:path.join(evidence,name+'-'+renderer+'-source.png')});
        assert.deepEqual(errors,[]);
        results.push({name,renderer,trial,inventory,ready_ms:ready,overview,source,selection,memory,page_errors:errors});
        console.log(JSON.stringify({name,renderer,trial,ready_ms:ready,overview_p95:percentile(overview.map(sample=>sample.handler_ms),.95),source_p95:percentile(source.map(sample=>sample.handler_ms),.95)}));
        await context.close();
      }
    }
    const summary=[];
    for(const [name] of cases)for(const renderer of ['svg','pixi']){
      const rows=results.filter(row=>row.name===name&&row.renderer===renderer),flatten=mode=>rows.flatMap(row=>row[mode]);
      const modes={};
      for(const mode of ['overview','source']){const samples=flatten(mode);modes[mode]={samples:samples.length,handler_p50_ms:percentile(samples.map(sample=>sample.handler_ms),.5),handler_p95_ms:percentile(samples.map(sample=>sample.handler_ms),.95),interaction_frame_p95_ms:percentile(samples.map(sample=>sample.interaction_frame_interval_ms),.95),two_frame_p95_ms:percentile(samples.map(sample=>sample.two_frame_ms),.95)};}
      summary.push({name,renderer,ready_median_ms:percentile(rows.map(row=>row.ready_ms),.5),ready_samples_ms:rows.map(row=>row.ready_ms),...modes,
        selection_handler_p95_ms:percentile(flatten('selection').map(sample=>sample.handler_ms),.95),js_heap_median_bytes:percentile(rows.map(row=>row.memory.js_heap_bytes),.5)});
    }
    const report={at:new Date().toISOString(),browser:browser.version(),cpu:os.cpus()[0].model,logical_cpus:os.cpus().length,platform:os.platform(),gpu,
      viewport:[1440,900],canvas:[1440,800],device_pixel_ratio:1,trials:3,samples_per_trial:20,inputs,summary,results,
      scope:'One laptop, headless Chromium with Intel D3D11 requested. Matched layout, graph and camera. Pixi is an isolated rendering/navigation prototype with plain source text. Full SVG includes product features. Frame intervals and two-frame waits are scheduling proxies. Memory is JavaScript heap, excluding GPU textures. No CPU throttling.'};
    fs.writeFileSync(path.join(evidence,'measurements.json'),JSON.stringify(report,null,2)+'\n');
    console.log(JSON.stringify({gpu,summary}));
  }finally{await browser.close();}
}
run().catch(error=>{console.error(error);process.exitCode=1;});
