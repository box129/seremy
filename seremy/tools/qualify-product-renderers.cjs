// Same full product/controller, same inputs and cameras, SVG versus opt-in Pixi paint.
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
function percentile(values,fraction){const sorted=[...values].sort((a,b)=>a-b);return Number(sorted[Math.ceil(sorted.length*fraction)-1].toFixed(2));}
async function wheels(page){return page.evaluate(async()=>{
  const map=document.querySelector('#map'),bounds=map.getBoundingClientRect(),rows=[];
  const frame=()=>new Promise(resolve=>requestAnimationFrame(resolve));let previous=await frame();
  for(let i=0;i<20;i++){
    const start=performance.now();map.dispatchEvent(new WheelEvent('wheel',{deltaY:i%2?60:-60,clientX:bounds.x+bounds.width/2,clientY:bounds.y+bounds.height/2,bubbles:true,cancelable:true}));
    const handler=performance.now()-start,first=await frame(),second=await frame();
    rows.push({handler_ms:handler,interaction_frame_interval_ms:first-previous,two_frame_ms:performance.now()-start});previous=second;
  }return rows;
});}
async function run(){
  const [redux,prepared,evidence]=process.argv.slice(2,5).map(value=>path.resolve(value));fs.mkdirSync(evidence,{recursive:true});
  const inputs=JSON.parse(fs.readFileSync(path.join(prepared,'inputs.json'),'utf8'));
  const cases=[['redux',redux],['synthetic',inputs.synthetic.publication],['pydantic',inputs.pydantic.publication]].filter(([name])=>!process.argv[5]||name===process.argv[5]);
  const browser=await chromium.launch({args:['--use-angle=d3d11','--enable-webgl','--ignore-gpu-blocklist','--enable-precise-memory-info']});
  const results=[];let gpu;
  try{
    for(const [name,publication] of cases){
      const map=path.join(publication,'map.html'),html=fs.readFileSync(map,'utf8');
      const data=JSON.parse(html.match(/<script id="fixture" type="application\/json">([\s\S]*?)<\/script>/)[1]);
      const edge=name==='redux'?data.edges.find(edge=>edge.from.file==='src/utils/isAction.ts'&&edge.to.file==='src/utils/isPlainObject.ts'):
        data.edges.find(edge=>Buffer.from(data.files[edge.from.file]).subarray(0,edge.from.start).toString().split('\n').length>80)||data.edges[0];
      const inventory={files:Object.keys(data.files).length,lines:Object.values(data.files).reduce((sum,text)=>sum+text.split('\n').length,0),source_sites:data.edges.length,digest:data.bundle.content_digest,map_bytes:fs.statSync(map).size};
      let expectedOverview,expectedSource;
      for(let trial=0;trial<3;trial++)for(const renderer of trial%2?['pixi','svg']:['svg','pixi']){
        const context=await browser.newContext({viewport:{width:1440,height:900},deviceScaleFactor:1}),page=await context.newPage(),errors=[];
        page.on('pageerror',error=>errors.push(error.message));
        const url=pathToFileURL(map);url.searchParams.set('renderer',renderer);
        const start=Date.now();await page.goto(url.href,{timeout:120000});
        await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('source verified'),null,{timeout:120000});
        const ready=Date.now()-start,info=await page.evaluate(()=>window.__seremyRendererInfo());assert.equal(info.engine,renderer);
        if(renderer==='pixi'){assert.equal(info.gl_error,0);gpu=info.renderer;}
        await page.addStyleTag({content:'#map{height:800px!important}'});await page.locator('#close-files').click();await page.locator('#fit').click();
        assert.deepEqual(await page.locator('#map').evaluate(node=>[node.clientWidth,node.clientHeight]),[1440,800]);
        const overviewCamera=await page.locator('#world').getAttribute('transform');expectedOverview??=overviewCamera;assert.equal(overviewCamera,expectedOverview);
        const overview=await wheels(page);
        await page.locator('#inspect').click();await page.locator('#edges').selectOption(edge.id);await page.locator('#origin').click();await page.locator('#close-inspector').click();
        const sourceCamera=await page.locator('#world').getAttribute('transform');expectedSource??=sourceCamera;assert.equal(sourceCamera,expectedSource);
        const source=await wheels(page);
        let cdp;if(name==='synthetic'&&trial===0){cdp=await context.newCDPSession(page);await cdp.send('Profiler.enable');await cdp.send('Profiler.start');}
        const selection=await page.evaluate(async ids=>{
          const picker=document.querySelector('#edges'),rows=[];
          for(let i=0;i<20;i++){
            const start=performance.now();picker.value=ids[i%ids.length];const assigned=performance.now();picker.dispatchEvent(new Event('change'));const changed=performance.now();
            await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
            rows.push({native_value_assignment_ms:assigned-start,handler_ms:changed-assigned,two_frame_ms:performance.now()-start});
          }return rows;
        },[edge.id,data.edges.at(-1).id]);
        let functions;
        if(cdp){const {profile}=await cdp.send('Profiler.stop');fs.writeFileSync(path.join(evidence,renderer+'-selection-cpu.json'),JSON.stringify(profile));
          functions=profile.nodes.map(node=>({name:node.callFrame.functionName||'(anonymous)',line:node.callFrame.lineNumber,hits:node.hitCount||0})).sort((a,b)=>b.hits-a.hits).slice(0,20);}
        const memory=await page.evaluate(()=>({js_heap_bytes:performance.memory?.usedJSHeapSize??null,dom_nodes:document.querySelectorAll('*').length,renderer:window.__seremyRendererInfo()}));
        if(trial===0){await page.locator('#origin').click();await page.screenshot({path:path.join(evidence,name+'-'+renderer+'-source.png')});}
        assert.deepEqual(errors,[]);
        results.push({name,renderer,trial,inventory,ready_ms:ready,overview,source,selection,memory,functions,page_errors:errors});
        fs.writeFileSync(path.join(evidence,'partial-results.json'),JSON.stringify(results,null,2)+'\n');
        console.log(JSON.stringify({name,renderer,trial,ready_ms:ready,source_handler_p95_ms:percentile(source.map(row=>row.handler_ms),.95)}));await context.close();
      }
    }
    const summary=[];
    for(const [name] of cases)for(const renderer of ['svg','pixi']){
      const rows=results.filter(row=>row.name===name&&row.renderer===renderer),modes={};
      for(const mode of ['overview','source','selection']){
        const samples=rows.flatMap(row=>row[mode]);modes[mode]={samples:samples.length,handler_p50_ms:percentile(samples.map(row=>row.handler_ms),.5),handler_p95_ms:percentile(samples.map(row=>row.handler_ms),.95),two_frame_p95_ms:percentile(samples.map(row=>row.two_frame_ms),.95)};
        if(mode==='selection')modes[mode].native_value_assignment_p95_ms=percentile(samples.map(row=>row.native_value_assignment_ms),.95);
        else modes[mode].interaction_frame_p95_ms=percentile(samples.map(row=>row.interaction_frame_interval_ms),.95);
      }
      summary.push({name,renderer,ready_median_ms:percentile(rows.map(row=>row.ready_ms),.5),js_heap_median_bytes:percentile(rows.map(row=>row.memory.js_heap_bytes),.5),...modes});
    }
    const report={at:new Date().toISOString(),browser:browser.version(),cpu:os.cpus()[0].model,gpu,viewport:[1440,900],canvas:[1440,800],device_pixel_ratio:1,trials:3,samples_per_trial:20,inputs,summary,results,
      scope:'One laptop, headless Chromium, requested D3D11 hardware. Same full controller, retained semantic SVG DOM, geometry, graph and camera. Pixi adds GPU paint, preserving the SVG input layer. Scheduling proxies are not compositor FPS. Memory excludes GPU texture allocation. Synthetic first-trial selection has CPU profiling overhead. No CPU throttling.'};
    fs.writeFileSync(path.join(evidence,'measurements.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({gpu,summary}));
  }finally{await browser.close();}
}
run().catch(error=>{console.error(error);process.exitCode=1;});
