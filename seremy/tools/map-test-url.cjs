const {pathToFileURL}=require('node:url');
const assert=require('node:assert/strict');

exports.pathToFileURL=file=>{
  const url=pathToFileURL(file);
  if(process.env.SEREMY_RENDERER)url.searchParams.set('renderer',process.env.SEREMY_RENDERER);
  return url;
};

exports.requireRenderer=async page=>{
  if(process.env.SEREMY_RENDERER!=='pixi')return;
  const info=await page.locator('body').evaluate(()=>window.__seremyRendererInfo());
  assert.equal(info.engine,'pixi',await page.locator('#renderer-status').textContent());
  assert.ok(info.objects>0&&info.text_objects>0);
  assert.equal(info.gl_error,0);
};

exports.selectRenderer=async scope=>{
  if(process.env.SEREMY_RENDERER!=='pixi')return;
  await scope.locator('#inspect').click();await scope.locator('#arrangement-tools summary').click();
  await scope.locator('#renderer').selectOption('pixi');await scope.locator('body[data-renderer=pixi]').waitFor();
  await exports.requireRenderer(scope);
  await scope.locator('#arrangement-tools summary').click();await scope.locator('#close-inspector').click();
};
