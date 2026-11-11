// MAP-A3-style acceptance checks on the REAL SEREMY bundle slice.
// Run: node check-map.cjs <seremy map dir>
// Verifies: no page errors, real source binding, the real isAction →
// isPlainObject edge followed to its declaration with Back restoring the
// view, provenance visible, collapse/expansion camera retention, and
// stale-embedding rejection (navigation disabled, STALE badge shown).

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const assert = require('node:assert/strict');

async function check() {
  const dir = path.resolve(process.argv[2]);
  const mapPath = path.join(dir, 'map.html');
  const browser = await chromium.launch(
    process.env.CHROME_BIN ? { executablePath: process.env.CHROME_BIN } : {}
  );
  try {
    const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
    const errors = [], checks = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(pathToFileURL(mapPath).href);

    // Binding: embedded source must verify against the bundle blobs.
    await page.waitForFunction(
      () => document.querySelector('#bind-state').textContent.includes('bound')
    );
    assert.match(await page.locator('#bind-state').innerText(), /^bound · bundle [0-9a-f]{12}$/);
    checks.push('Embedded real source verified against the bundle blob hashes at load time');

    const fixture = JSON.parse(await page.locator('#fixture').textContent());
    assert.equal(Object.keys(fixture.files).length, 2);
    assert.equal(fixture.edges.length, 1);
    assert.equal(fixture.edges[0].kind, 'CALLS');
    assert.equal(fixture.edges[0].origin, 'binder_observation');

    // Real slice geometry: two cards, one edge.
    assert.equal(await page.locator('.card').count(), 2);
    assert.equal(await page.locator('.hit').count(), 1);
    checks.push('Real slice renders: 2 source files, 1 statically bound edge');

    // MAP-A3: follow the real call occurrence to its declaration and Back.
    const map = page.locator('#map'), matrix = () => page.locator('#world').getAttribute('transform');
    const overview = await matrix();
    await page.getByRole('button', { name: 'Show source' }).click();
    assert.match(await page.locator('#detail').innerText(), /isAction\.ts:6 · isPlainObject/);
    const sourceView = await matrix();
    await page.getByRole('button', { name: 'Follow target' }).click();
    assert.match(await page.locator('#detail').innerText(), /isPlainObject\.ts:5 · isPlainObject/);
    assert.notEqual(await matrix(), sourceView);
    assert.match(await map.textContent(), /export default function isPlainObject/);
    await page.getByRole('button', { name: 'Back' }).click();
    assert.equal(await matrix(), sourceView);
    assert.match(await page.locator('#detail').innerText(), /isAction\.ts:6/);
    checks.push('Followed the real isPlainObject occurrence (bytes [185,198)) to its declaration (bytes [132,145)) and Back restored the exact camera');

    // Provenance from the bundle must be visible.
    const detail = await page.locator('#detail').innerText();
    assert.match(detail, /binder_observation/);
    assert.match(detail, /typescript-checker-v0\.2/);
    checks.push('Bundle provenance visible: origin binder_observation, binding profile typescript-checker-v0.2');

    // Collapse/expand retains camera.
    await page.getByRole('button', { name: 'Collapse utils' }).click();
    assert.equal(await page.locator('.card').count(), 0);
    assert.equal(await page.locator('.hit').count(), 0);
    assert.match(await page.locator('#map').textContent(), /utils\s*·\s*2 files/);
    await page.getByRole('button', { name: 'Expand utils' }).click();
    assert.equal(await page.locator('.card').count(), 2);
    assert.equal(await page.locator('.hit').count(), 1);
    assert.equal(await matrix(), sourceView);
    checks.push('Collapse/expand retained the source camera and the followed occurrence');

    // Fit restores overview.
    await page.getByRole('button', { name: 'Fit map' }).click();
    assert.equal(await matrix(), overview);

    // Stale rejection: tampered embedding must show STALE and disable follow.
    const original = fs.readFileSync(mapPath, 'utf-8');
    const tampered = original.replace(
      /"src\/utils\/isAction\.ts":\s*\{"text":\s*"(.{40})/,
      (match, head) => match.slice(0, -5) + 'XXXXX'
    );
    assert.notEqual(tampered, original, 'tamper must change the page');
    const tamperedPath = path.join(dir, 'map-tampered.html');
    fs.writeFileSync(tamperedPath, tampered);
    const stalePage = await browser.newPage({ viewport: { width: 1400, height: 900 } });
    const staleErrors = [];
    stalePage.on('pageerror', (error) => staleErrors.push(error.message));
    await stalePage.goto(pathToFileURL(tamperedPath).href);
    await stalePage.waitForFunction(
      () => document.querySelector('#bind-state').textContent.includes('STALE')
    );
    assert.match(await stalePage.locator('#bind-state').innerText(), /STALE/);
    assert.equal(await stalePage.getByRole('button', { name: 'Follow target' }).isDisabled(), true);
    assert.equal(await stalePage.getByRole('button', { name: 'Show source' }).isDisabled(), true);
    await stalePage.close();
    fs.unlinkSync(tamperedPath);
    checks.push('Tampered embedding detected: STALE badge shown, navigation disabled');
    assert.deepEqual(staleErrors, []);

    assert.deepEqual(errors, []);
    fs.writeFileSync(
      path.join(dir, '..', 'artifacts', 'map-checks.json'),
      JSON.stringify(
        {
          status: 'passed',
          scope: 'Real SEREMY graph bundle slice (2 files, 1 statically bound edge)',
          browser: browser.version(),
          viewport: [1400, 900],
          bundle: fixture.bundle,
          checks,
          pageErrors: errors,
          productionAcceptance: 'not_run',
          performanceBenchmark: 'not_run',
        },
        null,
        2
      ) + '\n'
    );
    console.log('checks passed:\n- ' + checks.join('\n- '));
  } finally {
    await browser.close();
  }
}
check().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
