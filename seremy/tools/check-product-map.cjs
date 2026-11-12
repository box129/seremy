// Browser integration checks on a real full-source publication.
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL,requireRenderer}=require('./map-test-url.cjs');
const assert=require('node:assert/strict');

async function run(){
  const root=path.resolve(process.argv[2]);
  const reportDir=path.resolve(process.argv[3]||path.join(root,'..','..','browser-evidence'));
  fs.mkdirSync(reportDir,{recursive:true});
  const browser=await chromium.launch(process.env.CHROME_BIN?{executablePath:process.env.CHROME_BIN}:{});
  const checks=[],errors=[];
  try{
    const page=await browser.newPage({viewport:{width:1500,height:1000}});
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto(pathToFileURL(path.join(root,'map.html')).href);
    await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('source verified'));
    await requireRenderer(page);
    const data=JSON.parse(await page.locator('#fixture').textContent());
    assert.equal(Object.keys(data.files).length,17);
    assert.ok(data.edges.length>1);
    checks.push('Full Redux source inventory loads and verifies all 17 source blobs');
    const edge=data.edges.find(e=>e.from.file==='src/utils/isAction.ts'&&e.to.file==='src/utils/isPlainObject.ts');
    assert.ok(edge);
    if (!await page.locator('#inspector').isVisible()) await page.locator('#inspect').click();
    await page.getByRole('combobox',{name:'Relationship',exact:true}).selectOption(edge.id);
    await page.getByRole('button',{name:'Show source',exact:true}).click();
    assert.match(await page.locator('#detail').innerText(),/isAction\.ts:6/);
    const origin=await page.locator('#world').getAttribute('transform');
    await page.getByRole('button',{name:'Follow target',exact:true}).click();
    assert.match(await page.locator('#detail').innerText(),/isPlainObject\.ts:5/);
    assert.match(await page.locator('#map').textContent(),/export default function isPlainObject/);
    await page.getByRole('button',{name:'Back',exact:true}).click();
    assert.equal(await page.locator('#world').getAttribute('transform'),origin);
    checks.push('Real call navigation and Back preserve source span and camera');
    await page.getByRole('button',{name:'Collapse folders',exact:true}).click();
    assert.equal(await page.locator('.file').count(),0);
    await page.getByRole('button',{name:'Expand folders',exact:true}).click();
    assert.equal(await page.locator('#world').getAttribute('transform'),origin);
    checks.push('Folder collapse hides source files and expansion preserves camera');
    await page.getByRole('searchbox',{name:'Find file or symbol'}).fill('isPlainObject');
    await page.getByRole('combobox',{name:'Open file'}).selectOption('src/utils/isPlainObject.ts');
    await page.getByRole('button',{name:'Open file',exact:true}).press('Enter');
    assert.match(await page.locator('#detail').innerText(),/isPlainObject\.ts:5/);
    checks.push('File/symbol search supports keyboard opening of source');
    const matrix=()=>page.locator('#world').getAttribute('transform');
    const before=await matrix();
    const rect=await page.locator('#map').boundingBox();
    const x=rect.width*.6,y=rect.height*.4;
    const nums=s=>s.match(/-?[\d.]+/g).map(Number);
    const [a,b,k]=nums(before);
    await page.mouse.move(rect.x+x,rect.y+y);await page.mouse.wheel(0,-200);
    await page.waitForFunction(old=>document.querySelector('#world').getAttribute('transform')!==old,before);
    const [c,d,j]=nums(await matrix());
    assert.ok(Math.hypot((x-a)/k*j+c-x,(y-b)/k*j+d-y)<1);
    checks.push('Pointer zoom retains source position within one CSS pixel');
    await page.screenshot({path:path.join(reportDir,'browser-source-view.png')});
    const minimap=page.locator('#mini'),miniRect=await minimap.boundingBox();
    const view=(await minimap.getAttribute('viewBox')).split(' ').map(Number);
    await page.mouse.click(miniRect.x+miniRect.width/2,miniRect.y+miniRect.height/2);
    const [mx,my,mk]=nums(await matrix());
    const miniScale=Math.min((miniRect.width-2)/view[2],(miniRect.height-2)/view[3]);
    assert.ok(Math.abs((rect.width/2-mx)/mk-view[2]/2)*miniScale<=1);
    assert.ok(Math.abs((rect.height/2-my)/mk-view[3]/2)*miniScale<=1);
    checks.push('Minimap center navigation accounts for SVG aspect ratio');

    const tampered=path.join(reportDir,'tampered-check.html');
    let html=fs.readFileSync(path.join(root,'map.html'),'utf8');
    html=html.replace('export default function isPlainObject','export default function FakePlainObject');
    fs.writeFileSync(tampered,html);
    try{
      await page.goto(pathToFileURL(tampered).href);
      await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('STALE'));
      assert.equal(await page.locator('#target').isDisabled(),true);
      checks.push('Changed embedded source disables relationship navigation');
    }finally{fs.unlinkSync(tampered);}
    assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(reportDir,'browser-checks.json'),JSON.stringify({
      status:'passed',browser:browser.version(),viewport:[1500,1000],
      content_digest:data.bundle.content_digest,checks,page_errors:errors,
      performance:'not_run',production_acceptance:'not_run'
    },null,2)+'\n');
    console.log(JSON.stringify({status:'passed',checks}));
  }finally{await browser.close();}
}
run().catch(e=>{console.error(e);process.exitCode=1;});
