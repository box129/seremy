// Compare the SVG viewer before and after folding using identical source/graph data.
const {chromium}=require('playwright');
const {execFileSync}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const {pathToFileURL}=require('node:url');
const assert=require('node:assert/strict');

function percentile(values,fraction){
  const sorted=[...values].sort((a,b)=>a-b);
  return Number(sorted[Math.ceil(sorted.length*fraction)-1].toFixed(2));
}

async function profile(page){
  const timings=await page.evaluate(async()=>{
    const map=document.querySelector('#map'),bounds=map.getBoundingClientRect();
    const handler=[],presented=[];
    for(let index=0;index<20;index++){
      const start=performance.now();
      map.dispatchEvent(new WheelEvent('wheel',{deltaY:index%2?60:-60,
        clientX:bounds.x+bounds.width/2,clientY:bounds.y+bounds.height/2,
        bubbles:true,cancelable:true}));
      handler.push(performance.now()-start);
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
      presented.push(performance.now()-start);
    }
    return {handler,presented,nodes:document.querySelector('#world').querySelectorAll('*').length};
  });
  return {samples:20,handler_p50_ms:percentile(timings.handler,.5),handler_p95_ms:percentile(timings.handler,.95),
    two_animation_frames_p95_ms:percentile(timings.presented,.95),svg_nodes:timings.nodes};
}

async function run(){
  const [redux,stress,evidence,scratch]=process.argv.slice(2,6).map(value=>path.resolve(value));
  const baselineCommit=process.argv[6]||'bd75e8e';
  fs.mkdirSync(evidence,{recursive:true});fs.mkdirSync(scratch,{recursive:true});
  const repository=path.resolve(__dirname,'../..');
  const baseline=execFileSync('git',['show',baselineCommit+':seremy/map/product-template.html'],{cwd:repository,encoding:'utf8'});
  const browser=await chromium.launch(process.env.CHROME_BIN?{executablePath:process.env.CHROME_BIN}:{});
  const results=[];
  try{
    for(const [name,publication] of [['redux',redux],['synthetic',stress]]){
      const current=fs.readFileSync(path.join(publication,'map.html'),'utf8');
      const fixture=current.match(/<script id="fixture" type="application\/json">([\s\S]*?)<\/script>/)[1];
      const data=JSON.parse(fixture);
      const inventory={files:Object.keys(data.files).length,
        lines:Object.values(data.files).reduce((count,text)=>count+text.split(/\r\n|\n/).length,0),sites:data.edges.length};
      if(name==='synthetic'){assert.equal(inventory.files,100);assert.equal(inventory.lines,50000);assert.equal(inventory.sites,5000);}
      for(const [version,html] of [['baseline',baseline.replace('FIXTURE_JSON',()=>fixture)],['updated',current]]){
        console.log('Profiling '+name+' '+version);
        const file=path.join(scratch,name+'-'+version+'.html');fs.writeFileSync(file,html);
        const page=await browser.newPage({viewport:{width:1440,height:900}});
        const errors=[];page.on('pageerror',error=>errors.push(error.message));
        const started=Date.now();await page.goto(pathToFileURL(file).href);
        await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('source verified'),{},{timeout:120000});
        const readyMs=Date.now()-started;
        const overview=await profile(page);
        await page.getByRole('combobox',{name:'Relationship',exact:true}).selectOption(data.edges[0].id);
        await page.getByRole('button',{name:'Show source',exact:true}).click();
        const source=await profile(page);
        assert.deepEqual(errors,[]);
        results.push({name,version,inventory,ready_ms:readyMs,overview,source,page_errors:errors});
        await page.close();
      }
    }
    const receipt={date:new Date().toISOString(),renderer:'SVG',baseline_commit:baselineCommit,
      browser:browser.version(),platform:os.platform(),cpu:os.cpus()[0].model,
      logical_cpus:os.cpus().length,viewport:[1440,900],results,
      limits:'One headless Chromium run per case, no CPU throttling. Synthetic workload. Two-frame timing includes browser scheduling. No GPU renderer comparison.'};
    fs.writeFileSync(path.join(evidence,'render-benchmark.json'),JSON.stringify(receipt,null,2)+'\n');
    console.log(JSON.stringify(receipt));
  }finally{await browser.close();}
}
run().catch(error=>{console.error(error);process.exitCode=1;});
