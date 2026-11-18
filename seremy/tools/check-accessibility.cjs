// Scoped accessibility inspection. Automated checks do not certify WCAG conformance.
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path');
const assert=require('node:assert/strict');
async function main(){
 const url=process.argv[2],out=path.resolve(process.argv[3]),axe=path.resolve(process.argv[4]);
 fs.mkdirSync(out,{recursive:true});const browser=await chromium.launch();const page=await browser.newPage({viewport:{width:1440,height:900}});
 const results={url,axeVersion:null,states:[],keyboard:[],errors:[]};page.on('pageerror',e=>results.errors.push(e.message));
 async function scan(name){
  const contexts=page.frames();
  for(const frame of contexts){
   if(frame!==page.mainFrame()&&(frame.url()==='about:blank'||!await(await frame.frameElement()).isVisible()))continue;
   await frame.addScriptTag({path:axe});
   const audit=await frame.evaluate(async()=>{const r=await axe.run(document,{iframes:false,runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa','wcag22aa']}});return {version:r.testEngine.version,violations:r.violations.map(v=>({id:v.id,impact:v.impact,help:v.help,url:v.helpUrl,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary,html:n.html}))})),incomplete:r.incomplete.map(v=>({id:v.id,nodes:v.nodes.length,details:v.nodes.map(n=>({target:n.target,html:n.html,summary:n.failureSummary}))})),passes:r.passes.length};});
   results.axeVersion=audit.version;results.states.push({name,frame:frame===page.mainFrame()?'launcher':'map',...audit});
  }
  await page.screenshot({path:path.join(out,name+'.png')});
 }
 try{
  await page.goto(url);await scan('landing');
  await page.locator('#empty-connect').click();await scan('repository-dialog');await page.locator('#close-connect').press('Escape');
  await page.locator('#try-example').click();const frame=page.frameLocator('#map');
  await frame.locator('#status').filter({hasText:'source verified'}).waitFor({timeout:120000});await scan('map');
  const data=JSON.parse(await frame.locator('#fixture').textContent());
  await frame.getByRole('checkbox',{name:'Show subtree types on map',exact:true}).uncheck();
  const hidden=Object.keys(data.files).filter(p=>p.startsWith('types/')).length;
  assert.equal(await frame.locator('#visible-file-count').innerText(),`${Object.keys(data.files).length-hidden} / ${Object.keys(data.files).length} visible`);
  await frame.getByRole('checkbox',{name:'Show subtree types on map',exact:true}).check();
  await frame.getByRole('button',{name:'Back',exact:true}).click();
  assert.equal(await frame.getByRole('checkbox',{name:'Show subtree types on map',exact:true}).isChecked(),false);
  await frame.getByRole('button',{name:'Restore all',exact:true}).click();
  results.folderControls='Separate heading/checkbox supports hiding, restoring, and Back';
  await frame.locator('#toggle-search').click();await frame.locator('#search').fill('isAction');await scan('search');await frame.locator('#search').press('Escape');
  await page.locator('#generate-documentation').click();await scan('generation-dialog');
  for(let i=0;i<10;i++){await page.keyboard.press('Tab');results.keyboard.push(await page.evaluate(()=>({outer:document.activeElement.id,inner:document.querySelector('#map').contentDocument?.activeElement?.id})));}
  assert.ok(results.keyboard.every(s=>s.outer==='map'),'Tab must stay in the documentation iframe');
  assert.equal(await page.locator('header').evaluate(e=>e.inert),true);
  await frame.getByRole('button',{name:'Close documentation request'}).focus();await page.keyboard.press('Shift+Tab');
  const lastEnabled=await frame.locator('dialog').evaluateAll(dialogs=>{
   const dialog=dialogs.find(d=>!d.hidden&&getComputedStyle(d).display!=='none');
   return [...dialog.querySelectorAll('button,input,select,textarea,a[href],[tabindex]')].filter(e=>!e.disabled&&e.tabIndex>=0&&e.getClientRects().length).at(-1).id;
  });
  assert.equal(await frame.locator('body').evaluate(e=>e.ownerDocument.activeElement.id),lastEnabled);
  await frame.locator('#documentation-purpose').press('Escape');
  await page.waitForFunction(()=>document.activeElement?.id==='generate-documentation');
  assert.equal(await page.locator('header').evaluate(e=>e.inert),false);
  await page.locator('#doc-tab').click();await scan('documentation');
  await page.setViewportSize({width:320,height:640});await scan('documentation-320');
  await page.addStyleTag({content:'p{line-height:1.5!important;margin-bottom:2em!important}body{letter-spacing:.12em!important;word-spacing:.16em!important}'});
  await scan('text-spacing-320');
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Text-spacing override must not overflow the page');
  const fontRules=await page.locator('body,button,summary,p,label,h1,h2,h3,a,select,input,textarea').evaluateAll(es=>es.map(e=>({tag:e.tagName,font:parseFloat(getComputedStyle(e).fontSize)})));
  await page.locator('body,button,summary,p,label,h1,h2,h3,a,select,input,textarea').evaluateAll(es=>{const sizes=es.map(e=>parseFloat(getComputedStyle(e).fontSize));es.forEach((e,i)=>e.style.fontSize=sizes[i]*2+'px');});
  await scan('text-doubled-320');results.textResize={method:'Computed HTML text sizes explicitly doubled with inline CSS; not native browser zoom',baselineElements:fontRules.length};
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Doubled text must not overflow the page');
  await page.locator('#generate-documentation').click();await scan('generation-dialog-320');
  results.overflow=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
  assert.ok(results.overflow.scroll<=results.overflow.width,'No horizontal page overflow at 320px');
  results.contrastSamples=[['Landing text against brightest background dot','#aaaaaa','#363636'],['Source line numbers','#aaaaaa','#1e1e1e'],['Documentation form text','#dddddd','#232323'],['Source code','#cccccc','#1e1e1e']].map(([label,fg,bg])=>{
   const lum=h=>{const c=h.slice(1).match(/../g).map(x=>parseInt(x,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return c[0]*.2126+c[1]*.7152+c[2]*.0722;};
   const a=lum(fg),b=lum(bg),ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);assert.ok(ratio>=4.5);return {label,foreground:fg,background:bg,ratio,threshold:4.5};
  });
  assert.ok(results.states.every(s=>s.violations.length===0),'axe detected a confirmed violation; inspect audit.json');
 }finally{fs.writeFileSync(path.join(out,'audit.json'),JSON.stringify(results,null,2));await browser.close();}
 console.log(JSON.stringify({states:results.states.map(s=>({name:s.name,frame:s.frame,violations:s.violations.map(v=>({id:v.id,nodes:v.nodes.length})),incomplete:s.incomplete.map(v=>({id:v.id,nodes:v.nodes}))})),keyboard:results.keyboard,errors:results.errors},null,2));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
