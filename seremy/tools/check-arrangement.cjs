// Real pointer movement, grouping, navigation and browser-local view persistence.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');

async function geometry(page){
  return page.locator('.file').evaluateAll(nodes=>Object.fromEntries(nodes.map(node=>[node.dataset.file,
    [Number(node.getAttribute('x')),Number(node.getAttribute('y'))]])));
}
async function clickFile(page,file,shift=false){
  const rect=await page.locator('.file[data-file="'+file+'"]').boundingBox();
  assert.ok(rect&&rect.width>0&&rect.height>0);
  if(shift)await page.keyboard.down('Shift');
  await page.mouse.click(rect.x+rect.width/2,rect.y+rect.height/2);
  if(shift)await page.keyboard.up('Shift');
}
async function run(){
  const publication=path.resolve(process.argv[2]),evidence=path.resolve(process.argv[3]);
  fs.mkdirSync(evidence,{recursive:true});
  const browser=await chromium.launch(process.env.CHROME_BIN?{executablePath:process.env.CHROME_BIN}:{});
  const errors=[],checks=[];
  try{
    const page=await browser.newPage({viewport:{width:1440,height:900}});
    page.on('pageerror',error=>errors.push(error.message));
    const url=pathToFileURL(path.join(publication,'map.html')).href;
    await page.goto(url);
    await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('source verified'));
    const canonical=await page.locator('#fixture').textContent();
    const data=JSON.parse(canonical);
    const file='src/utils/isAction.ts',second='src/utils/isPlainObject.ts';
    await page.locator('#arrange').click();
    await page.locator('#close-inspector').click();
    await page.locator('#close-files').click();
    const before=await geometry(page),rect=await page.locator('.file[data-file="'+file+'"]').boundingBox();
    const scale=await page.locator('#world').evaluate(node=>Number(node.getAttribute('transform').match(/scale\(([^)]+)\)/)[1]));
    await page.mouse.move(rect.x+rect.width/2,rect.y+rect.height/2);
    await page.mouse.down();await page.mouse.move(rect.x+rect.width/2+25,rect.y+rect.height/2+15,{steps:4});await page.mouse.up();
    const moved=await geometry(page);
    assert.ok(Math.abs(moved[file][0]-before[file][0]-25/scale)<.01);
    assert.ok(Math.abs(moved[file][1]-before[file][1]-15/scale)<.01);
    assert.deepEqual(moved[second],before[second]);
    await page.locator('#back').click();
    assert.deepEqual(await geometry(page),before);
    checks.push('Dragging moves the selected file in world coordinates, preserves siblings and supports Back');
    const folderPoint=await page.locator('.folder[data-directory="src/utils"]').evaluate(node=>{
      const point=new DOMPoint(Number(node.getAttribute('x'))+4,Number(node.getAttribute('y'))+8).matrixTransform(document.querySelector('#world').getScreenCTM());
      return {x:point.x,y:point.y};
    });
    await page.mouse.move(folderPoint.x,folderPoint.y);await page.mouse.down();
    await page.mouse.move(folderPoint.x+15,folderPoint.y+10,{steps:4});await page.mouse.up();
    const folderMoved=await geometry(page);
    for(const name of [file,second]){
      assert.ok(Math.abs(folderMoved[name][0]-before[name][0]-15/scale)<.01);
      assert.ok(Math.abs(folderMoved[name][1]-before[name][1]-10/scale)<.01);
    }
    await page.locator('#back').click();assert.deepEqual(await geometry(page),before);
    checks.push('Dragging a nested folder moves its descendants together and Back restores their positions');

    await clickFile(page,file);
    await clickFile(page,second,true);
    assert.equal(await page.locator('.arranged-selection').count(),2);
    await page.locator('#inspect').click();
    await page.locator('#group-name').fill('Utilities');
    await page.locator('#group-selection').click();
    assert.equal(await page.getByRole('button',{name:'Select group Utilities',exact:true}).count(),1);
    await page.locator('#close-inspector').click();
    const grouped=await geometry(page);
    const groupRect=await page.getByRole('button',{name:'Select group Utilities',exact:true}).boundingBox();
    await page.mouse.move(groupRect.x+groupRect.width/2,groupRect.y+groupRect.height/2);
    await page.mouse.down();await page.mouse.move(groupRect.x+groupRect.width/2+10,groupRect.y+groupRect.height/2+10,{steps:4});await page.mouse.up();
    const draggedGroup=await geometry(page);
    for(const name of [file,second])assert.ok(Math.abs(draggedGroup[name][0]-grouped[name][0]-10/scale)<.01);
    await page.locator('#back').click();assert.deepEqual(await geometry(page),grouped);
    await page.locator('#map').focus();await page.keyboard.press('ArrowRight');
    const shifted=await geometry(page);
    for(const name of [file,second])assert.ok(Math.abs(shifted[name][0]-grouped[name][0]-10)<.01);
    await page.locator('#back').click();assert.deepEqual(await geometry(page),grouped);
    checks.push('Shift selection creates a named group and keyboard movement moves its members together');

    await page.locator('#arrange').click();
    await page.locator('#edges').selectOption(data.edges.find(edge=>edge.from.file===file&&edge.to.file===second).id);
    await page.locator('#origin').click();
    const atSource=await page.locator('#world').getAttribute('transform');
    await page.locator('#target').click();await page.locator('#back').click();
    assert.equal(await page.locator('#world').getAttribute('transform'),atSource);
    await page.getByRole('navigation',{name:'Source breadcrumbs'}).getByRole('button',{name:'utils',exact:true}).click();
    assert.notEqual(await page.locator('#world').getAttribute('transform'),atSource);
    await page.locator('#back').click();assert.equal(await page.locator('#world').getAttribute('transform'),atSource);
    await page.locator('#layout-mode').selectOption('columns');
    const columns=await geometry(page);assert.notDeepEqual(columns,grouped);
    await page.locator('#back').click();assert.equal(await page.locator('#layout-mode').inputValue(),'packed');
    await page.locator('#collapse').click();
    await page.locator('#fit').click();
    await page.locator('#save-view').click();
    await page.locator('#view-status').filter({hasText:'View saved'}).waitFor();
    const stored=await page.evaluate(()=>Object.entries(localStorage).find(([key])=>key.startsWith('["seremy-view",')));
    assert.ok(stored);
    await page.reload();
    await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('source verified'));
    await page.locator('#inspect').click();await page.locator('#arrangement-tools summary').click();
    await page.locator('#restore-view').click();
    assert.equal(await page.locator('#view-status').textContent(),'Saved view restored.');
    assert.equal(await page.locator('.file').count(),0);
    await page.locator('#collapse').click();
    await page.locator('#fit').click();
    // Call navigation had opened the source file, while the arrangement itself persists.
    const restored=await geometry(page);
    assert.deepEqual(restored[file],grouped[file]);assert.deepEqual(restored[second],grouped[second]);
    assert.equal(await page.getByRole('button',{name:'Select group Utilities',exact:true}).count(),1);
    assert.equal(await page.locator('#fixture').textContent(),canonical);
    await page.screenshot({path:path.join(evidence,'arrangement.png')});
    checks.push('Layout changes, source navigation, breadcrumbs, collapse and reload preserve saved positions and canonical evidence');

    const camera=await page.locator('#world').getAttribute('transform');
    await page.evaluate(([key,text])=>{const state=JSON.parse(text);state.digest='different-snapshot';localStorage.setItem(key,JSON.stringify(state));},stored);
    await page.locator('#restore-view').click();
    assert.match(await page.locator('#view-status').textContent(),/incompatible or damaged/);
    assert.equal(await page.locator('#world').getAttribute('transform'),camera);
    await page.evaluate(([key,text])=>{const state=JSON.parse(text);state.arrangement.placements.packed['file:src/utils/isAction.ts']={x:null,y:52};localStorage.setItem(key,JSON.stringify(state));},stored);
    await page.locator('#restore-view').click();
    assert.match(await page.locator('#view-status').textContent(),/incompatible or damaged/);
    assert.equal(await page.locator('#world').getAttribute('transform'),camera);
    await page.evaluate(()=>{Storage.prototype.setItem=()=>{throw new DOMException('Storage unavailable','QuotaExceededError');};});
    await page.locator('#save-view').click();assert.match(await page.locator('#view-status').textContent(),/unavailable or full/);
    checks.push('Mismatched snapshots, damaged coordinates and unavailable storage leave the current view usable');
    await page.screenshot({path:path.join(evidence,'storage-error.png')});
    assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(evidence,'checks.json'),JSON.stringify({status:'passed',checks,page_errors:errors},null,2)+'\n');
    console.log(JSON.stringify({status:'passed',checks}));
  }finally{await browser.close();}
}
run().catch(error=>{console.error(error);process.exitCode=1;});
