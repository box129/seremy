// Ensure coarse relationships account for every occurrence and retain exact navigation.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');

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
    const data=JSON.parse(await page.locator('#fixture').textContent());
    const groups=await page.locator('.wire[data-overview=true]').evaluateAll(nodes=>nodes.map(node=>Number(node.dataset.siteCount)));
    assert.ok(groups.length>0&&groups.length<data.edges.length);
    assert.equal(groups.reduce((sum,count)=>sum+count,0),data.edges.length);
    assert.ok(groups.some(count=>count>1));
    checks.push('Overview groups represent every original source occurrence');

    const edge=data.edges.at(-1);
    await page.getByRole('combobox',{name:'Relationship',exact:true}).selectOption(edge.id);
    assert.equal(await page.locator('.wire.selected').getAttribute('data-edge'),edge.id);
    assert.equal(await page.locator('.wire.selected').getAttribute('data-overview'),'false');
    await page.getByRole('button',{name:'Follow target',exact:true}).click();
    assert.equal(await page.locator('#tree button[aria-current=true]').getAttribute('data-file'),edge.to.file);
    await page.getByRole('button',{name:'Back',exact:true}).click();
    assert.equal(await page.locator('.wire.selected').getAttribute('data-edge'),edge.id);
    checks.push('Any occurrence can be selected, followed and restored from the overview');

    await page.getByRole('button',{name:'Collapse folders',exact:true}).click();
    const collapsed=await page.locator('.wire[data-overview=true]').count();
    assert.ok(collapsed>0&&collapsed<groups.length);
    const count=await page.locator('.wire[data-overview=true]').evaluateAll(nodes=>nodes.reduce((sum,node)=>sum+Number(node.dataset.siteCount),0));
    assert.equal(count,data.edges.length);
    await page.getByRole('button',{name:'Expand folders',exact:true}).click();
    assert.equal(await page.locator('.wire[data-overview=true]').count(),groups.length);
    checks.push('Folder collapse recomputes groups and expansion restores them without losing occurrences');
    assert.deepEqual(errors,[]);
    await page.screenshot({path:path.join(evidence,'overview.png')});
    const receipt={status:'passed',checks,page_errors:errors};
    fs.writeFileSync(path.join(evidence,'checks.json'),JSON.stringify(receipt,null,2)+'\n');
    console.log(JSON.stringify(receipt));
  }finally{await browser.close();}
}
run().catch(error=>{console.error(error);process.exitCode=1;});
