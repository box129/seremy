// Real bounded-source navigation, keyboard controls, saved offsets and GPU clipping.
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const {spawnSync}=require('node:child_process');
const {pathToFileURL}=require('node:url');
const assert=require('node:assert/strict');

async function run(){
  const evidence=path.resolve(process.argv[2]);fs.mkdirSync(evidence,{recursive:true});
  const input=fs.mkdtempSync(path.join(os.tmpdir(),'seremy-source-window-'));
  let publication;
  try{
    fs.writeFileSync(path.join(input,'entry.ts'),'import { chosen } from "./target";\r\nexport function start(){\r\n\tconst label="é🦊";'+ ' '.repeat(420)+'chosen(); const tail="'+ 'z'.repeat(450)+'";\r\n}\r\n');
    fs.writeFileSync(path.join(input,'target.ts'),'export const prefix="é🦊'+ 'x'.repeat(420)+'"; export function chosen(){return 7;}\r\n');
    fs.writeFileSync(path.join(input,'big.ts'),'import { chosen } from "./target";\nexport function large(){'+ ' '.repeat(20000)+'chosen();}\n');
    const result=spawnSync(process.env.PYTHON||'python',['-B','-m','seremy','analyze',input,'--output',path.join(evidence,'publication')],{cwd:path.resolve(__dirname,'../..'),encoding:'utf8',windowsHide:true,timeout:60000});
    assert.equal(result.status,0,result.stderr);publication=JSON.parse(result.stdout);
  }finally{
    assert.equal(path.dirname(input),path.resolve(os.tmpdir()));assert.match(path.basename(input),/^seremy-source-window-/);
    fs.rmSync(input,{recursive:true,force:true});
  }
  const browser=await chromium.launch({...(process.env.CHROME_BIN?{executablePath:process.env.CHROME_BIN}:{}),args:['--use-angle=d3d11','--enable-webgl','--ignore-gpu-blocklist']});
  const checks=[],errors=[],clipping=[],renderers=[];
  async function state(page){return page.evaluate(()=>({camera:document.querySelector('#world').getAttribute('transform'),edge:document.querySelector('#edges').value,offset:document.querySelector('#source-scroll').value,focus:[...document.querySelectorAll('.source-focus')].map(node=>[node.dataset.file,node.dataset.start,node.dataset.end])}));}
  async function alignment(page,span){
    const error=await page.evaluate(span=>{
      const data=JSON.parse(document.querySelector('#fixture').textContent),prefix=new TextDecoder().decode(new TextEncoder().encode(data.files[span.file]).slice(0,span.start));
      const lines=prefix.split(/\r\n|\n/),row=[...document.querySelectorAll('.code[data-file]')].find(node=>node.dataset.file===span.file&&Number(node.dataset.line)===lines.length);
      const index=lines.at(-1).replace(/\t/g,'    ').length-Number(row.dataset.renderStart),point=row.querySelector('tspan[x]').getStartPositionOfChar(index);
      const focus=document.querySelector('.source-focus'),token=[...document.querySelectorAll('.token')].find(node=>node.dataset.file===span.file&&Number(node.dataset.start)===span.start);
      const group=token.parentElement,clip=document.querySelector(group.getAttribute('clip-path').slice(4,-1)+' rect');
      return {focus:Math.abs(Number(focus.getAttribute('x'))-point.x),token:Math.abs(Number(token.getAttribute('x'))-point.x),inside:Number(token.getAttribute('x'))>=Number(clip.getAttribute('x'))&&Number(token.getAttribute('x'))+Number(token.getAttribute('width'))<=Number(clip.getAttribute('x'))+Number(clip.getAttribute('width'))+1,rendered:row.textContent.length};
    },span);
    assert.ok(error.focus<1&&error.token<1&&error.inside,JSON.stringify(error));assert.ok(error.rendered<400);
  }
  try{
    for(const renderer of ['svg','pixi']){
      const page=await browser.newPage({viewport:{width:1440,height:900}});page.on('pageerror',error=>errors.push(error.message));
      const url=pathToFileURL(publication.map);url.searchParams.set('renderer',renderer);await page.goto(url.href);
      await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('source verified'));
      const rendering=await page.evaluate(()=>window.__seremyRendererInfo());assert.equal(rendering.engine,renderer);renderers.push(rendering);
      assert.ok(await page.getByRole('button',{name:/^Reveal later columns in/}).count()>=3);
      assert.ok(await page.getByRole('button',{name:/^Reveal later columns in/}).evaluateAll(nodes=>nodes.every(node=>node.getAttribute('aria-disabled')==='false'&&node.getAttribute('tabindex')==='0')));
      const canonical=await page.locator('#fixture').textContent(),data=JSON.parse(canonical);
      const edge=data.edges.find(edge=>edge.from.file==='entry.ts'),big=data.edges.find(edge=>edge.from.file==='big.ts');assert.ok(edge&&big);
      for(const viewport of [{width:1440,height:900},{width:1280,height:800},{width:1225,height:580}]){
        await page.setViewportSize(viewport);const before=await page.locator('#world').getAttribute('transform');
        await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
        await page.locator('#map').focus();await page.keyboard.press('/');await page.locator('#file-finder').waitFor();
        assert.equal(await page.locator('#search').evaluate(node=>node===document.activeElement),true);
        assert.equal(await page.locator('#world').getAttribute('transform'),before);
        await page.keyboard.press('Escape');assert.equal(await page.locator('#toggle-search').evaluate(node=>node===document.activeElement),true);
        const layout=await page.evaluate(()=>({viewport:[innerWidth,innerHeight],document:[document.documentElement.scrollWidth,document.documentElement.scrollHeight],header:document.querySelector('header').getBoundingClientRect().height,overflow:document.documentElement.scrollWidth>innerWidth||document.documentElement.scrollHeight>innerHeight,controls:[...document.querySelectorAll('header button')].every(node=>{const b=node.getBoundingClientRect();return b.x>=0&&b.right<=innerWidth&&b.bottom<=48;})}));
        if(layout.overflow)await page.screenshot({path:path.join(evidence,'overflow.png')});
        assert.ok(layout.header<=46&&!layout.overflow&&layout.controls,JSON.stringify(layout));
      }
      await page.locator('#toggle-search').click();await page.locator('#search').fill('no-such-source-zzzz');
      assert.equal(await page.locator('#open').isDisabled(),true);assert.match(await page.locator('#finder-status').textContent(),/No files or symbols/);
      await page.locator('#search').fill('chosen');assert.equal(await page.locator('#open').isEnabled(),true);await page.keyboard.press('Escape');
      checks.push(renderer+': compact controls and Find keyboard/focus behavior fit three desktop viewports without moving the camera');
      await page.setViewportSize({width:1440,height:900});await page.locator('#inspect').click();await page.locator('#edges').selectOption(edge.id);await page.locator('#origin').click();
      assert.ok(Number(await page.locator('#source-scroll').inputValue())>1000);
      assert.ok(await page.locator('.file').evaluateAll(nodes=>nodes.every(node=>Number(node.getAttribute('width'))<=760)));
      await alignment(page,edge.from);const origin=await state(page);
      await page.screenshot({path:path.join(evidence,renderer+'-long-source.png')});
      if(renderer==='pixi'){
        const padding=await page.evaluate(span=>{
          const file=document.querySelector('.file[data-file="'+span.file+'"]'),focus=document.querySelector('.source-focus'),map=document.querySelector('#map'),b=map.getBoundingClientRect();
          const matrix=document.querySelector('#world').getScreenCTM();
          const point=new DOMPoint(Number(file.getAttribute('x'))+Number(file.getAttribute('width'))-14,Number(focus.getAttribute('y'))+1).matrixTransform(matrix);
          map.dispatchEvent(new WheelEvent('wheel',{deltaY:0,clientX:b.x+b.width/2,clientY:b.y+b.height/2,bubbles:true,cancelable:true}));
          const canvas=document.querySelector('#pixi-surface'),gl=canvas.getContext('webgl2'),ratio=canvas.width/b.width,width=Math.max(1,Math.floor(12*matrix.a*ratio)),height=Math.max(1,Math.floor(12*matrix.d*ratio)),pixels=new Uint8Array(width*height*4);
          gl.readPixels(Math.floor((point.x-b.x)*ratio),canvas.height-Math.floor((point.y-b.y)*ratio)-height,width,height,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
          let keywordPixels=0,opaque=0;for(let i=0;i<pixels.length;i+=4){if(pixels[i]>pixels[i+1]+3&&pixels[i+2]>pixels[i]+3)keywordPixels++;if(pixels[i+3]===255)opaque++;}
          return {keyword_pixels_in_padding:keywordPixels,opaque,pixels:width*height,error:gl.getError()};
        },edge.from);
        assert.equal(padding.error,0);assert.equal(padding.keyword_pixels_in_padding,0,JSON.stringify(padding));assert.ok(padding.opaque>padding.pixels/2,JSON.stringify(padding));clipping.push(padding);
      }
      await page.locator('#target').click();assert.ok(Number(await page.locator('#source-scroll').inputValue())>1000);await alignment(page,edge.to);
      await page.locator('#back').click();assert.deepEqual(await state(page),origin);
      checks.push(renderer+': bounded cards automatically reveal distant caller/declaration columns with exact Unicode/tab/CRLF alignment and Back restoration');
      await page.locator('#source-scroll').focus();await page.keyboard.press('Home');assert.equal(await page.locator('#source-scroll').inputValue(),'0');
      await page.locator('#back').click();assert.deepEqual(await state(page),origin);
      await page.getByRole('button',{name:'Reveal earlier columns in entry.ts',exact:true}).press('Enter');assert.ok(Number(await page.locator('#source-scroll').inputValue())<Number(origin.offset));
      await page.locator('#back').click();assert.deepEqual(await state(page),origin);
      const slider=await page.locator('#source-scroll').boundingBox();
      await page.mouse.move(slider.x+slider.width*.6,slider.y+slider.height/2);await page.mouse.down();
      await page.mouse.move(slider.x+slider.width*.8,slider.y+slider.height/2,{steps:4});await page.mouse.up();
      assert.notEqual(await page.locator('#source-scroll').inputValue(),origin.offset);
      await page.locator('#back').click();assert.deepEqual(await state(page),origin);await alignment(page,edge.from);
      checks.push(renderer+': the range and per-file keyboard controls move source horizontally and Back restores the offset');
      await page.locator('#arrangement-tools summary').click();await page.locator('#save-view').click();
      const stored=await page.evaluate(()=>Object.entries(localStorage).find(([key])=>key.startsWith('["seremy-view",')));assert.ok(JSON.parse(stored[1]).sourceOffsets['entry.ts']>1000);
      await page.reload();await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('source verified'));
      await page.locator('#inspect').click();await page.locator('#arrangement-tools summary').click();await page.locator('#restore-view').click();
      if(renderer==='pixi')await page.locator('body[data-renderer=pixi]').waitFor();assert.deepEqual(await state(page),origin);await alignment(page,edge.from);
      const before=await state(page);await page.evaluate(([key,value])=>{const view=JSON.parse(value);view.sourceOffsets['entry.ts']=-1;localStorage.setItem(key,JSON.stringify(view));},stored);await page.locator('#restore-view').click();
      assert.match(await page.locator('#view-status').textContent(),/damaged/);assert.deepEqual(await state(page),before);
      await page.evaluate(([key,value])=>{const view=JSON.parse(value);delete view.sourceOffsets;localStorage.setItem(key,JSON.stringify(view));},stored);await page.locator('#restore-view').click();
      if(renderer==='pixi')await page.locator('body[data-renderer=pixi]').waitFor();await alignment(page,edge.from);
      checks.push(renderer+': saved offsets survive reload, invalid values are rejected and older views reveal long-line evidence');
      await page.locator('#edges').selectOption(big.id);await page.locator('#origin').click();await alignment(page,big.from);
      await page.locator('#target').click();await page.locator('#region-tools summary').click();
      const declaration=data.entities.find(entity=>entity.file_id==='target.ts'&&entity.name==='chosen');
      await page.locator('#regions').selectOption(declaration.entity_id);assert.equal(await page.locator('#edges').inputValue(),'');
      await page.locator('#source-scroll').focus();await page.keyboard.press('Home');assert.equal(await page.locator('#source-scroll').inputValue(),'0');
      assert.equal(await page.locator('#origin').isEnabled(),true);await page.locator('#origin').click();assert.ok(Number(await page.locator('#source-scroll').inputValue())>1000);
      assert.equal(await page.evaluate(()=>window.__seremyRendererInfo().engine),renderer);assert.equal(await page.locator('#fixture').textContent(),canonical);
      checks.push(renderer+': a call beyond 20,000 characters renders only a visible source slice without changing canonical evidence or losing the renderer');
      await page.close();
    }
    assert.deepEqual(errors,[]);const result={status:'passed',browser:browser.version(),executable:process.env.CHROME_BIN||'playwright-chromium',renderers,checks,clipping,page_errors:errors};fs.writeFileSync(path.join(evidence,'checks.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
  }finally{await browser.close();}
}
run().catch(error=>{console.error(error);process.exitCode=1;});
