const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
async function run(){
  const [publication,prototype,evidence]=process.argv.slice(2).map(value=>path.resolve(value));
  fs.mkdirSync(evidence,{recursive:true});
  const browser=await chromium.launch({args:['--use-angle=d3d11','--enable-webgl','--ignore-gpu-blocklist']});
  const results=[];
  try{
    for(const [renderer,file] of [['svg',path.join(publication,'map.html')],['pixi',prototype]]){
      const page=await browser.newPage({viewport:{width:1440,height:900}});
      await page.goto(pathToFileURL(file).href,{timeout:120000});
      await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('source verified'),{},{timeout:120000});
      const data=JSON.parse(await page.locator('#fixture').textContent());
      if(renderer==='svg')await page.locator('#inspect').click();
      await page.locator('#edges').selectOption(data.edges[0].id);await page.locator('#origin').click();
      const cdp=await page.context().newCDPSession(page);await cdp.send('Profiler.enable');await cdp.send('Profiler.start');
      const samples=await page.evaluate(async ids=>{
        const picker=document.querySelector('#edges'),rows=[];
        for(let i=0;i<6;i++){
          const start=performance.now();picker.value=ids[i%2];const assigned=performance.now();picker.dispatchEvent(new Event('change'));const changed=performance.now();
          await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
          rows.push({native_value_assignment_ms:assigned-start,change_handler_ms:changed-assigned,two_frame_ms:performance.now()-start});
        }
        return rows;
      },[data.edges[0].id,data.edges.at(-1).id]);
      const {profile}=await cdp.send('Profiler.stop');
      const functions=profile.nodes.map(node=>({name:node.callFrame.functionName||'(anonymous)',line:node.callFrame.lineNumber,hits:node.hitCount||0})).sort((a,b)=>b.hits-a.hits).slice(0,20);
      fs.writeFileSync(path.join(evidence,renderer+'-selection-cpu.json'),JSON.stringify(profile));
      results.push({renderer,samples,functions});console.log(JSON.stringify(results.at(-1)));await page.close();
    }
    fs.writeFileSync(path.join(evidence,'selection-diagnosis.json'),JSON.stringify({browser:browser.version(),results},null,2)+'\n');
  }finally{await browser.close();}
}
run().catch(error=>{console.error(error);process.exitCode=1;});
