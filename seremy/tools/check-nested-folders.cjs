const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL,requireRenderer}=require('./map-test-url.cjs');

async function state(page){
  return page.evaluate(()=>({
    camera:document.querySelector('#world').getAttribute('transform'),
    folders:[...document.querySelectorAll('.folder')].map(node=>[
      node.dataset.directory,...['x','y','width','height'].map(key=>Number(node.getAttribute(key)))
    ]),
    expanded:[...document.querySelectorAll('#world [aria-expanded]')].map(node=>[
      node.getAttribute('aria-label'),node.getAttribute('aria-expanded')
    ])
  }));
}

async function run(){
  const publication=path.resolve(process.argv[2]),evidence=path.resolve(process.argv[3]);
  fs.mkdirSync(evidence,{recursive:true});
  const browser=await chromium.launch(process.env.CHROME_BIN?{executablePath:process.env.CHROME_BIN}:{});
  const checks=[],errors=[];
  try{
    const page=await browser.newPage({viewport:{width:1440,height:900}});
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(pathToFileURL(path.join(publication,'map.html')).href);
    await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('source verified'));
    const original=await state(page);
    const parent=original.folders.find(folder=>folder[0]==='src');
    for(const child of original.folders.filter(folder=>folder[0]!=='src')){
      assert.ok(child[1]>=parent[1]&&child[2]>parent[2]);
      assert.ok(child[1]+child[3]<=parent[1]+parent[3]&&child[2]+child[4]<=parent[2]+parent[4]);
    }
    await page.screenshot({path:path.join(evidence,'nested-overview.png')});
    checks.push('Redux types and utils folders are geometrically contained by src');
    await page.getByRole('button',{name:'Collapse src/utils',exact:true}).press('Enter');
    assert.equal(await page.locator('.file[data-file^="src/utils/"]').count(),0);
    assert.ok(await page.locator('.file[data-file^="src/types/"]').count()>0);
    assert.equal(await page.locator('.token[data-file^="src/utils/"]').count(),0);
    const collapsed=await state(page);
    await page.screenshot({path:path.join(evidence,'utils-collapsed.png')});
    await page.getByRole('button',{name:'Expand src/utils',exact:true}).press('Space');
    assert.deepEqual(await state(page),original);
    checks.push('Keyboard collapse hides only utils and expansion restores the original layout and camera');
    await page.getByRole('button',{name:'Back',exact:true}).click();
    assert.deepEqual(await state(page),collapsed);
    await requireRenderer(page);
    const data=JSON.parse(await page.locator('#fixture').textContent());
    const edge=data.edges.find(edge=>!edge.from.file.startsWith('src/utils/')&&edge.to.file.startsWith('src/utils/'));
    assert.ok(edge);
    if (!await page.locator('#inspector').isVisible()) await page.locator('#inspect').click();
    await page.getByRole('combobox',{name:'Relationship',exact:true}).selectOption(edge.id);
    const beforeFollow=await state(page);
    const anchor=await page.evaluate(id=>{
      const wire=[...document.querySelectorAll('.wire')].find(node=>node.dataset.edge===id);
      const end=wire.getPointAtLength(wire.getTotalLength());
      const folder=document.querySelector('.folder[data-directory="src/utils"]');
      return {end:[end.x,end.y],expected:['x','y'].map((key,index)=>Number(folder.getAttribute(key))+Number(folder.getAttribute(index?'height':'width'))/2)};
    },edge.id);
    assert.ok(Math.hypot(anchor.end[0]-anchor.expected[0],anchor.end[1]-anchor.expected[1])<1);
    await page.getByRole('button',{name:'Follow target',exact:true}).click();
    assert.ok(await page.getByRole('button',{name:'Collapse src/utils',exact:true}).count());
    assert.equal(await page.locator('.source-focus').getAttribute('data-file'),edge.to.file);
    await page.getByRole('button',{name:'Back',exact:true}).click();
    assert.deepEqual(await state(page),beforeFollow);
    checks.push('Cross-folder relationship ends at the collapsed boundary, Follow reveals its source, and Back restores collapse');
    await page.getByRole('button',{name:'Collapse src',exact:true}).press('Enter');
    assert.equal(await page.locator('.folder').count(),1);
    assert.equal(await page.locator('.file').count(),0);
    await page.getByRole('button',{name:'Expand src',exact:true}).press('Enter');
    assert.ok(await page.getByRole('button',{name:'Expand src/utils',exact:true}).count());
    checks.push('Collapsing a parent preserves the independent collapsed state of its child');
    assert.deepEqual(errors,[]);
    const receipt={status:'passed',browser:browser.version(),checks,page_errors:errors};
    fs.writeFileSync(path.join(evidence,'nested-folder-checks.json'),JSON.stringify(receipt,null,2)+'\n');
    console.log(JSON.stringify(receipt));
  }finally{await browser.close();}
}
run().catch(error=>{console.error(error);process.exitCode=1;});
