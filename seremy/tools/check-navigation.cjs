// Exercise source selection through the repository tree and the actual call hitbox.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');

async function state(page) {
  return page.evaluate(() => ({
    camera: document.querySelector('#world').getAttribute('transform'),
    detail: document.querySelector('#detail').textContent,
    edge: document.querySelector('#edges').value,
    focus: [...document.querySelectorAll('.source-focus')].map(node => [
      node.dataset.file, node.dataset.start, node.dataset.end
    ]),
    file: document.querySelector('#tree [aria-current=true]')?.dataset.file,
    expanded: [...document.querySelectorAll('#tree details[open]')].map(node => node.dataset.directory),
    scroll: document.querySelector('#repository').scrollTop
  }));
}

async function run() {
  const publication = path.resolve(process.argv[2]);
  const evidence = path.resolve(process.argv[3]);
  fs.mkdirSync(evidence, {recursive:true});
  const browser = await chromium.launch(process.env.CHROME_BIN ? {executablePath:process.env.CHROME_BIN} : {});
  const errors = [], checks = [];
  try {
    const page = await browser.newPage({viewport:{width:1440,height:900}});
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(pathToFileURL(path.join(publication, 'map.html')).href);
    await page.waitForFunction(() => document.querySelector('#status').textContent.includes('source verified'));
    const data = JSON.parse(await page.locator('#fixture').textContent());
    assert.equal(Object.keys(data.files).length, 17);
    const src = page.locator('details[data-directory="src"]');
    await src.locator(':scope > summary').click();
    const utils = page.locator('details[data-directory="src/utils"]');
    await utils.locator(':scope > summary').click();
    await page.getByRole('button', {name:'Open src/utils/isAction.ts',exact:true}).click();
    assert.match((await state(page)).detail, /isAction.ts:1/);
    checks.push('Expand src and utils, then open a real Redux file from the tree');

    const edge = data.edges.find(edge => edge.from.file === 'src/utils/isAction.ts' && edge.to.file === 'src/utils/isPlainObject.ts');
    assert.ok(edge);
    const call = page.locator(`.token[data-file="${edge.from.file}"][data-start="${edge.from.start}"]`);
    await call.click();
    assert.equal((await state(page)).edge, edge.id);
    assert.match((await state(page)).detail, /isAction.ts:6/);
    await page.getByRole('button', {name:'Zoom in',exact:true}).click();
    // Pan at blank canvas space, away from source hitboxes.
    const bounds = await page.locator('#map').boundingBox();
    await page.mouse.move(bounds.x+20,bounds.y+20);
    await page.mouse.down();
    await page.mouse.move(bounds.x+67,bounds.y+51,{steps:4});
    await page.mouse.up();
    const origin = await state(page);
    assert.deepEqual(origin.focus, [[edge.from.file,String(edge.from.start),String(edge.from.end)]]);
    const alignment = await page.evaluate(span => {
      const source = JSON.parse(document.querySelector('#fixture').textContent).files[span.file];
      const prefix = new TextDecoder().decode(new TextEncoder().encode(source).slice(0,span.start));
      const parts = prefix.split(/\r\n|\n/);
      const line = [...document.querySelectorAll('.code')].find(node =>
        node.dataset.file === span.file && Number(node.dataset.line) === parts.length);
      const text = line.querySelector('tspan[x]');
      const character = text.getStartPositionOfChar(parts.at(-1).replace(/\t/g,'    ').length);
      const highlight = document.querySelector('.source-focus');
      return Math.abs(Number(highlight.getAttribute('x'))-character.x);
    },edge.from);
    assert.ok(alignment < 1, 'Source highlight must align with rendered call text');
    await page.screenshot({path:path.join(evidence,'redux-call-selected.png')});
    await page.getByRole('button', {name:'Follow target',exact:true}).click();
    const destination = await state(page);
    assert.match(destination.detail, /isPlainObject.ts:5/);
    assert.equal(destination.file, edge.to.file);
    assert.notEqual(destination.camera, origin.camera);
    await page.screenshot({path:path.join(evidence,'redux-declaration.png')});
    await page.getByRole('button', {name:'Back',exact:true}).click();
    assert.deepEqual(await state(page), origin);
    checks.push('Click the call in source, zoom and pan, follow the declaration, and restore all navigation state with Back');

    await page.getByRole('button', {name:'Open src/createStore.ts',exact:true}).click();
    // Following a relationship reveals its target directory, which Back must undo.
    await utils.locator(':scope > summary').click();
    await page.getByRole('combobox', {name:'Relationship',exact:true}).selectOption(edge.id);
    const beforeReveal = await state(page);
    assert.ok(!beforeReveal.expanded.includes('src/utils'));
    await page.getByRole('button', {name:'Follow target',exact:true}).click();
    assert.ok((await state(page)).expanded.includes('src/utils'));
    await page.getByRole('button', {name:'Back',exact:true}).click();
    assert.deepEqual(await state(page), beforeReveal);
    checks.push('Following reveals the target folder and Back restores the prior tree expansion');
    assert.deepEqual(errors, []);
    const receipt = {status:'passed',browser:browser.version(),viewport:[1440,900],
      content_digest:data.bundle.content_digest,checks,origin,destination,page_errors:errors};
    fs.writeFileSync(path.join(evidence,'navigation-checks.json'),JSON.stringify(receipt,null,2)+'\n');
    console.log(JSON.stringify({status:'passed',checks}));
  } finally {await browser.close();}
}
run().catch(error => {console.error(error);process.exitCode=1;});
