const {chromium} = require('playwright');
const {spawnSync} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const {pathToFileURL} = require('node:url');
const assert = require('node:assert/strict');

async function run() {
  const redux = path.resolve(process.argv[2]);
  const evidence = path.resolve(process.argv[3]);
  const input = fs.mkdtempSync(path.join(os.tmpdir(), 'seremy-map-review-'));
  fs.mkdirSync(evidence, {recursive:true});
  fs.writeFileSync(path.join(input, 'long.py'), '\n'.repeat(160000) + 'def main(): pass\nmain()\n');
  const result = spawnSync(process.env.PYTHON || 'python', [
    '-B', '-m', 'seremy', 'analyze', input, '--output', path.join(evidence, 'many-lines-output')
  ], {cwd:path.resolve(__dirname, '../..'), windowsHide:true, encoding:'utf8', timeout:60000});
  fs.rmSync(input, {recursive:true, force:true});
  assert.equal(result.status, 0, result.stderr);
  const generated = JSON.parse(result.stdout);
  const browser = await chromium.launch(process.env.CHROME_BIN ? {executablePath:process.env.CHROME_BIN} : {});
  const checks = [];
  try {
    for (const [name, file] of [['redux', path.join(redux, 'map.html')], ['many-lines', generated.map]]) {
      const page = await browser.newPage({viewport:{width:1500,height:1000}});
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(pathToFileURL(file).href);
      await page.waitForFunction(() => document.querySelector('#status').textContent.includes('source verified'));
      const status = await page.locator('#status').innerText();
      if (name === 'redux') {
        assert.match(status, /17 files · 25 relationships · 30 source sites/);
        checks.push('Redux reports 25 distinct relationships separately from 30 source sites');
      } else {
        assert.match(status, /1 files · 1 relationships · 1 source sites/);
        const foldedCamera=await page.locator('#world').getAttribute('transform');
        const foldedHeight=await page.locator('.file').getAttribute('height');
        assert.ok(Number(foldedHeight)<2000);
        assert.equal(await page.getByRole('button',{name:'Expand full file long.py',exact:true}).count(),1);
        await page.getByRole('searchbox', {name:'Find file or symbol'}).fill('main');
        await page.getByRole('button', {name:'Open file', exact:true}).click();
        assert.match(await page.locator('#detail').innerText(), /long.py:160001/);
        assert.match(await page.locator('#world').textContent(), /def main/);
        await page.getByRole('button',{name:'Back',exact:true}).click();
        assert.equal(await page.locator('.file').getAttribute('height'),foldedHeight);
        assert.equal(await page.locator('#world').getAttribute('transform'),foldedCamera);
        await page.getByRole('button',{name:'Expand full file long.py',exact:true}).press('Enter');
        assert.ok(Number(await page.locator('.file').getAttribute('height'))>3000000);
        await page.getByRole('button',{name:'Fold file long.py',exact:true}).press('Space');
        assert.equal(await page.locator('.file').getAttribute('height'),foldedHeight);
        const data=JSON.parse(await page.locator('#fixture').textContent());
        if (!await page.locator('#inspector').isVisible()) await page.locator('#inspect').click();
        await page.getByRole('combobox',{name:'Relationship',exact:true}).selectOption(data.edges[0].id);
        const beforeFollow=await page.locator('#world').getAttribute('transform');
        await page.getByRole('button',{name:'Follow target',exact:true}).click();
        assert.match(await page.locator('#detail').innerText(), /long.py:160001/);
        assert.match(await page.locator('#world').textContent(), /def main/);
        await page.getByRole('button',{name:'Back',exact:true}).click();
        assert.equal(await page.locator('.file').getAttribute('height'),foldedHeight);
        assert.equal(await page.locator('#world').getAttribute('transform'),beforeFollow);
        checks.push('160,001st-line declaration opens through search and call navigation, restores folding through Back, and supports keyboard expansion');
      }
      assert.deepEqual(errors, []);
      await page.screenshot({path:path.join(evidence, name + '.png')});
      await page.close();
    }
    const receipt = {status:'passed',browser:browser.version(),checks};
    fs.writeFileSync(path.join(evidence,'review-map-checks.json'),JSON.stringify(receipt,null,2)+'\n');
    console.log(JSON.stringify(receipt));
  } finally {await browser.close();}
}
run().catch(error => {console.error(error);process.exitCode=1;});
