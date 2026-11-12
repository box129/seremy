const {chromium}=require('playwright');
const {execFileSync}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const assert=require('node:assert/strict');

async function run(){
  const [publication,evidence]=process.argv.slice(2).map(value=>path.resolve(value));
  fs.mkdirSync(evidence,{recursive:true});
  const current=fs.readFileSync(path.join(publication,'map.html'),'utf8');
  const fixture=current.match(/<script id="fixture" type="application\/json">([\s\S]*?)<\/script>/)[1];
  const template=execFileSync('git',['show','dc1b014:seremy/map/product-template.html'],{cwd:path.resolve(__dirname,'../..'),encoding:'utf8'});
  const baseline=path.join(evidence,'uncached-svg.html');fs.writeFileSync(baseline,template.replace('FIXTURE_JSON',()=>fixture));
  const browser=await chromium.launch({...process.env.CHROME_BIN?{executablePath:process.env.CHROME_BIN}:{},args:['--use-angle=d3d11','--enable-webgl','--ignore-gpu-blocklist']});
  const results=[];
  try{
    for(let trial=0;trial<3;trial++)for(const version of trial%2?['cached','uncached']:['uncached','cached']){
      const context=await browser.newContext({viewport:{width:1440,height:900}}),page=await context.newPage();
      const errors=[];page.on('pageerror',error=>errors.push(error.message));
      const start=Date.now();await page.goto(pathToFileURL(version==='uncached'?baseline:path.join(publication,'map.html')).href,{timeout:120000});
      await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('source verified'),{},{timeout:120000});
      const ready_ms=Date.now()-start;
      assert.equal(await page.locator('#files option').count(),100);assert.deepEqual(errors,[]);
      results.push({version,trial,ready_ms});console.log(JSON.stringify(results.at(-1)));await context.close();
    }
    fs.writeFileSync(path.join(evidence,'glyph-cache-measurements.json'),JSON.stringify({browser:browser.version(),baseline_commit:'dc1b014',results,
      scope:'Three alternating fresh browser contexts per variant on the identical 100-file source and graph. Startup includes source hash verification. Browser and operating-system caches can remain warm.'},null,2)+'\n');
  }finally{await browser.close();}
}
run().catch(error=>{console.error(error);process.exitCode=1;});
