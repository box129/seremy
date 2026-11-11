const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');

async function run(){
  const publication=path.resolve(process.argv[2]),evidence=path.resolve(process.argv[3]);
  fs.mkdirSync(evidence,{recursive:true});
  const browser=await chromium.launch(process.env.CHROME_BIN?{executablePath:process.env.CHROME_BIN}:{});
  const errors=[],checks=[];
  try{
    const page=await browser.newPage({viewport:{width:1440,height:900}});
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(pathToFileURL(path.join(publication,'map.html')).href);
    await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('source verified'));
    const data=JSON.parse(await page.locator('#fixture').textContent());
    const allEdges=await page.locator('.wire').count();assert.ok(allEdges>0);
    await page.getByRole('searchbox',{name:'Find file or symbol'}).fill('isAction');
    await page.getByRole('button',{name:'Open file',exact:true}).click();
    const file=await page.locator('.file[data-file="src/utils/isAction.ts"]').elementHandle();
    await page.getByRole('button',{name:'Zoom in',exact:true}).click();
    assert.equal(await file.evaluate(node=>node===document.querySelector('.file[data-file="src/utils/isAction.ts"]')),true);
    checks.push('Visible source file retains its DOM node during zoom');
    assert.ok(await page.locator('.wire[data-overview=false]').count()<data.edges.length);
    checks.push('Source zoom culls offscreen relationships');
    const bounds=await page.locator('#map').boundingBox();
    await page.mouse.move(bounds.x+20,bounds.y+20);await page.mouse.down();
    await page.mouse.move(bounds.x+50,bounds.y+40);
    await page.mouse.move(bounds.x+200000,bounds.y+200000);await page.mouse.up();
    assert.equal(await page.locator('.wire').count(),0);
    assert.equal(await file.evaluate(node=>node.isConnected),false);
    await page.getByRole('button',{name:'Fit map',exact:true}).click();
    assert.equal(await page.locator('.wire').count(),allEdges);
    checks.push('Leaving the scene evicts file and edge nodes, and Fit restores relationships');
    const edge=data.edges.find(edge=>edge.from.file==='src/utils/isAction.ts'&&edge.to.file==='src/utils/isPlainObject.ts');
    await page.getByRole('combobox',{name:'Relationship',exact:true}).selectOption(edge.id);
    await page.getByRole('button',{name:'Show source',exact:true}).click();
    assert.equal(await page.locator('.wire.selected').count(),1);
    await page.getByRole('button',{name:'Follow target',exact:true}).click();
    assert.match(await page.locator('#detail').innerText(),/isPlainObject.ts:5/);
    checks.push('Selected relationship remains available and navigable after culling and restoration');
    assert.deepEqual(errors,[]);
    await page.screenshot({path:path.join(evidence,'retained-source.png')});
    const receipt={status:'passed',browser:browser.version(),checks,page_errors:errors};
    fs.writeFileSync(path.join(evidence,'retained-renderer-checks.json'),JSON.stringify(receipt,null,2)+'\n');
    console.log(JSON.stringify(receipt));
  }finally{await browser.close();}
}
run().catch(error=>{console.error(error);process.exitCode=1;});
