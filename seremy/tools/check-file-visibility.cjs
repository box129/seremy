// Real source-map working sets: visibility, aggregation, navigation and saved views.
const {chromium}=require('playwright');
const {spawnSync}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {pathToFileURL}=require('node:url');
const assert=require('node:assert/strict');

async function run(){
  const evidence=path.resolve(process.argv[2]);fs.mkdirSync(evidence,{recursive:true});
  const input=fs.mkdtempSync(path.join(os.tmpdir(),'seremy-visibility-'));let publication;
  try{
    const sources={'src/entry.ts':'import { chosen } from "../lib/target";\nexport function entry(){ chosen(); return chosen(); }\n',
      'src/sibling.ts':'import { chosen } from "../lib/target";\nexport function sibling(){return chosen();}\n',
      'lib/target.ts':'export function chosen(){return 7;}\n','lib/extra.ts':'export function extra(){return 8;}\n'};
    for(const [name,text] of Object.entries(sources)){const file=path.join(input,name);fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,text);}
    const result=spawnSync(process.env.PYTHON||'python',['-B','-m','seremy','analyze',input,'--output',path.join(evidence,'publication')],
      {cwd:path.resolve(__dirname,'../..'),encoding:'utf8',windowsHide:true,timeout:60000});
    assert.equal(result.status,0,result.stderr);publication=JSON.parse(result.stdout);
  }finally{
    assert.equal(path.dirname(input),path.resolve(os.tmpdir()));assert.match(path.basename(input),/^seremy-visibility-/);fs.rmSync(input,{recursive:true,force:true});
  }
  const browser=await chromium.launch({...(process.env.CHROME_BIN?{executablePath:process.env.CHROME_BIN}:{}),args:['--use-angle=d3d11','--enable-webgl','--ignore-gpu-blocklist']});
  const checks=[],errors=[],renderers=[];
  async function state(page){return page.evaluate(()=>({camera:document.querySelector('#world').getAttribute('transform'),
    included:[...document.querySelectorAll('[data-visibility-file]')].filter(node=>node.checked).map(node=>node.dataset.visibilityFile),
    edge:document.querySelector('#edges').value,focus:[...document.querySelectorAll('.source-focus')].map(node=>[node.dataset.file,node.dataset.start,node.dataset.end]),
    tree:[...document.querySelectorAll('#tree details[open]')].map(node=>node.dataset.directory),
    folders:[...document.querySelectorAll('#world [aria-expanded]')].map(node=>[node.getAttribute('aria-label'),node.getAttribute('aria-expanded')])}));}
  async function inspector(page){if(!await page.locator('#inspector').isVisible())await page.locator('#inspect').click();}
  try{
    for(const renderer of ['svg','pixi']){
      const page=await browser.newPage({viewport:{width:1440,height:900}});page.on('pageerror',error=>errors.push(error.message));
      const url=pathToFileURL(publication.map);url.searchParams.set('renderer',renderer);await page.goto(url.href);
      await page.locator('#status').filter({hasText:'source verified'}).waitFor();
      const info=await page.evaluate(()=>window.__seremyRendererInfo());assert.equal(info.engine,renderer);renderers.push(info);
      const canonical=await page.locator('#fixture').textContent(),data=JSON.parse(canonical),graphPath=path.join(publication.publication,'graph.json'),graph=fs.readFileSync(graphPath,'utf8');
      assert.equal(data.edges.length,3);assert.equal(new Set(data.edges.map(edge=>edge.relation_id)).size,2);
      const file=name=>page.getByRole('checkbox',{name:'Show '+name+' on map',exact:true});
      const subtree=name=>page.getByRole('checkbox',{name:'Show subtree '+name+' on map',exact:true});
      await page.locator('#tree details').evaluateAll(nodes=>nodes.forEach(node=>node.open=true));
      assert.equal(await page.locator('#visible-file-count').innerText(),'4 / 4 visible');
      await page.locator('#collapse').click();await page.locator('#fit').click();for(let i=0;i<3;i++)await page.locator('#out').click();
      assert.equal(await page.locator('.wire').count(),1);assert.equal(await page.locator('.wire').getAttribute('data-site-count'),'3');
      const tree=await page.locator('#tree details[open]').count();
      await file('src/sibling.ts').uncheck();assert.equal(await page.locator('#visible-file-count').innerText(),'3 / 4 visible');
      assert.equal(await subtree('src').evaluate(node=>node.indeterminate),true);assert.equal(await page.locator('#tree details[open]').count(),tree);
      assert.equal(await page.locator('.wire').count(),1);assert.equal(await page.locator('.wire').getAttribute('data-site-count'),'2');
      assert.match(await page.locator('#world').textContent(),/1 of 2 files included/);
      await file('lib/target.ts').uncheck();assert.equal(await page.locator('.wire').count(),0);
      await inspector(page);assert.equal(await page.locator('#edges option').count(),4);assert.match(await page.locator('#connection-count').innerText(),/0 relationships · 0 source sites.*3 source sites hidden/);
      await page.locator('#back').click();assert.equal(await page.locator('.wire').getAttribute('data-site-count'),'2');
      await page.locator('#back').click();assert.equal(await page.locator('.wire').getAttribute('data-site-count'),'3');
      checks.push(renderer+': file hiding preserves sibling/target folders, tri-state subtree controls and exact collapsed relationship/site counts');

      await page.locator('#collapse').click();const edge=data.edges.find(edge=>edge.from.file==='src/entry.ts');
      await page.locator('#edges').selectOption(edge.id);await page.locator('#origin').click();
      await file('lib/target.ts').focus();await page.keyboard.press('Space');assert.equal(await file('lib/target.ts').isChecked(),false);
      const hiddenTarget=await state(page);assert.equal(await page.locator('.file[data-file="lib/target.ts"]').count(),0);
      await page.locator('#target').click();assert.equal(await file('lib/target.ts').isChecked(),true);
      assert.ok(await page.locator('.file[data-file="lib/target.ts"]').count());
      await page.locator('#back').click();assert.deepEqual(await state(page),hiddenTarget);
      checks.push(renderer+': keyboard file toggling and Follow target reveal only the target; one Back restores visibility, selection, camera and folders');

      await subtree('src').uncheck();assert.equal(await subtree('src').isChecked(),false);assert.equal(await subtree('src').evaluate(node=>node.indeterminate),false);
      assert.equal(await page.locator('.folder[data-directory="src"]').count(),0);
      const hiddenSubtree=await state(page);await page.locator('#breadcrumbs').getByRole('button',{name:'src',exact:true}).click();
      assert.equal(await subtree('src').isChecked(),true);await page.locator('#back').click();assert.deepEqual(await state(page),hiddenSubtree);
      await subtree('lib').check();await subtree('lib').uncheck();assert.equal(await page.locator('#visible-file-count').innerText(),'0 / 4 visible');
      assert.equal(await page.locator('#working-set-empty').isVisible(),true);assert.equal(await page.locator('.file,.folder,.wire').count(),0);assert.equal(await page.locator('#mini').isVisible(),false);
      const empty=await state(page);await page.locator('#toggle-search').click();await page.locator('#search').fill('lib/target');await page.locator('#search').press('Enter');
      assert.equal(await page.locator('#visible-file-count').innerText(),'1 / 4 visible');assert.equal(await file('lib/target.ts').isChecked(),true);
      await page.locator('#back').click();assert.deepEqual(await state(page),empty);
      await page.locator('#restore-visible-files').click();assert.equal(await page.locator('#visible-file-count').innerText(),'4 / 4 visible');assert.equal(await page.locator('#working-set-empty').isVisible(),false);
      await page.locator('#back').click();assert.deepEqual(await state(page),empty);await page.locator('#restore-all-files').click();
      checks.push(renderer+': whole subtrees, hidden-folder breadcrumbs, empty-map recovery, hidden-file Find and Restore all all preserve Back history');

      await file('lib/target.ts').uncheck();await file('src/sibling.ts').uncheck();
      await page.locator('#arrangement-tools').evaluate(node=>node.open=true);await page.locator('#save-view').click();const savedState=await state(page);
      const stored=await page.evaluate(()=>Object.entries(localStorage).find(([key])=>key.startsWith('["seremy-view",')));assert.ok(stored);
      assert.deepEqual(JSON.parse(stored[1]).hiddenFiles.sort(),['lib/target.ts','src/sibling.ts']);
      await page.reload();await page.locator('#status').filter({hasText:'source verified'}).waitFor();assert.equal(await page.locator('#visible-file-count').innerText(),'4 / 4 visible');
      await inspector(page);await page.locator('#arrangement-tools').evaluate(node=>node.open=true);await page.locator('#restore-view').click();
      if(renderer==='pixi')await page.locator('body[data-renderer=pixi]').waitFor();assert.deepEqual(await state(page),savedState);
      for(const invalid of [null,'src/entry.ts',['missing.ts'],['src/entry.ts','src/entry.ts'],[{}]]){
        await page.evaluate(({stored,invalid})=>{const view=JSON.parse(stored[1]);view.hiddenFiles=invalid;localStorage.setItem(stored[0],JSON.stringify(view));},{stored,invalid});
        await page.locator('#restore-view').click();assert.match(await page.locator('#view-status').innerText(),/damaged/);assert.deepEqual(await state(page),savedState);
      }
      await page.evaluate(stored=>{const view=JSON.parse(stored[1]);delete view.hiddenFiles;localStorage.setItem(stored[0],JSON.stringify(view));},stored);await page.locator('#restore-view').click();
      assert.equal(await page.locator('#visible-file-count').innerText(),'4 / 4 visible');await page.locator('#back').click();assert.deepEqual(await state(page),savedState);
      checks.push(renderer+': saved visibility survives reload; unknown, duplicate and malformed paths are rejected atomically; older views restore all files');

      for(const viewport of [{width:1440,height:900},{width:1280,height:800},{width:1225,height:580}]){
        await page.setViewportSize(viewport);await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
        const dimensions=await page.evaluate(()=>({viewport:[innerWidth,innerHeight],document:[document.documentElement.scrollWidth,document.documentElement.scrollHeight],overflow:document.documentElement.scrollWidth>innerWidth||document.documentElement.scrollHeight>innerHeight}));
        if(dimensions.overflow)await page.screenshot({path:path.join(evidence,'overflow.png')});assert.equal(dimensions.overflow,false,JSON.stringify(dimensions));
        assert.equal(await page.locator('#visible-file-count').isVisible(),true);
      }
      assert.equal(await page.locator('#fixture').textContent(),canonical);assert.equal(fs.readFileSync(graphPath,'utf8'),graph);
      assert.equal(await page.evaluate(()=>window.__seremyRendererInfo().engine),renderer);
      await page.screenshot({path:path.join(evidence,renderer+'-working-set.png')});
      checks.push(renderer+': three desktop sizes retain working-set controls and both renderers keep canonical graph/source bytes unchanged');
      await page.close();
    }
    assert.deepEqual(errors,[]);const result={status:'passed',browser:browser.version(),executable:process.env.CHROME_BIN||'playwright-chromium',renderers,checks,page_errors:errors,publication};
    fs.writeFileSync(path.join(evidence,'checks.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
  }finally{await browser.close();}
}
run().catch(error=>{console.error(error);process.exitCode=1;});
