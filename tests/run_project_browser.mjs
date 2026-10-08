// Real project browser checks and optional review evidence. Loopback only.
import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';
import { createRequire } from 'node:module';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import net from 'node:net';
import { spawn } from 'node:child_process';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
let playwright;
try { playwright = require('playwright'); }
catch { playwright = require(join(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES, 'playwright')); }
const { chromium } = playwright;
const executablePath = process.env.STAGE6_CHROMIUM_EXECUTABLE || chromium.executablePath();
assert(existsSync(executablePath), 'Preinstalled Chromium required');
const directory = dirname(fileURLToPath(import.meta.url));
const socket = net.createServer();
await new Promise(resolve => socket.listen(0, '127.0.0.1', resolve));
const port = socket.address().port;
await new Promise(resolve => socket.close(resolve));
const origin = `http://127.0.0.1:${port}`;
const credentials = { username: randomBytes(16).toString('hex'), password: randomBytes(24).toString('hex') };
const server = spawn(process.env.STAGE6_TEST_PYTHON || 'python', ['-B', join(directory, 'local_browser_server.py')], {
  cwd: dirname(directory), env: { ...process.env,
    STAGE6_TEST_USERNAME: credentials.username, STAGE6_TEST_PASSWORD: credentials.password,
    STAGE6_TEST_PORT: String(port) }, stdio: ['ignore', 'pipe', 'pipe'],
});
let errors = '';
server.stderr.on('data', data => { errors += data; });
let browser;
const diagnostics = { pageErrors: [], externalRequests: [], brokenImages: [], layouts: [] };
try {
  for (let attempt = 0; attempt < 100; attempt++) {
    if (server.exitCode !== null) throw new Error(`Server exited: ${errors.slice(-1500)}`);
    try { if ((await fetch(origin)).ok) break; } catch { /* Startup pending. */ }
    if (attempt === 99) throw new Error('Local server did not start');
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  browser = await chromium.launch({ executablePath, headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ httpCredentials: credentials,
    extraHTTPHeaders: { Authorization: `Basic ${Buffer.from(`${credentials.username}:${credentials.password}`).toString("base64")}` } });
  // Existing consent must never enable Google requests on a protected draft.
  await context.addInitScript(() => localStorage.setItem('nhp_analytics_choice_v1', 'accepted'));
  await context.route('**/*', route => {
    if (new URL(route.request().url()).origin === origin) return route.continue();
    diagnostics.externalRequests.push(route.request().url());
    return route.abort();
  });
  const page = await context.newPage();
  page.on('pageerror', error => diagnostics.pageErrors.push(error.message));
  const evidence = process.env.PROJECT_EVIDENCE_DIR ? resolve(process.env.PROJECT_EVIDENCE_DIR) : null;
  if (evidence) mkdirSync(evidence, { recursive: true });
  const path = '/projects/ensuite-renovation-merrow-guildford';
  const anonymous = await browser.newContext();
  assert.equal((await anonymous.request.get(origin + path)).status(), 404);
  assert.equal((await anonymous.request.get(origin + '/projects')).status(), 200);
  for (const [name, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
    await page.setViewportSize({ width, height });
    const response = await page.goto(origin + path);
    assert.equal(response.status(), 200);
    assert.match(response.headers()['x-robots-tag'], /noindex/);
    const decline = page.getByRole('button', { name: 'Decline', exact: true });
    if (await decline.isVisible()) await decline.click();
    await page.waitForLoadState('networkidle');
    assert.equal(await page.locator('main h1').textContent(), 'Ensuite renovation in Merrow, Guildford');
    assert.equal(await page.locator('main img').count(), 9);
    for (const image of await page.locator('main img').all()) {
      await image.scrollIntoViewIfNeeded();
      try {
        await image.evaluate(async img => { await img.decode(); });
      } catch (error) {
        console.error('Project image decode state:', JSON.stringify(await image.evaluate(img => ({
          src: img.src, currentSrc: img.currentSrc, srcset: img.srcset,
          complete: img.complete, naturalWidth: img.naturalWidth, loading: img.loading,
        }))));
        throw error;
      }
    }
    const dimensions = await page.evaluate(() => ({ width: innerWidth,
      document: document.documentElement.scrollWidth,
      images: [...document.querySelectorAll('main img')].map(img => ({ alt: img.alt,
        loaded: img.complete && img.naturalWidth > 0, width: img.width, source: img.currentSrc, defaultSource: img.src })) }));
    assert(dimensions.document <= dimensions.width, `Horizontal overflow at ${width}`);
    for (const img of dimensions.images) {
      assert(img.loaded && img.alt, 'Image decode/alt failed');
      assert(img.source.startsWith(origin + '/project-images/'), 'Unexpected image source');
    }
    assert.equal(await page.locator('cite').textContent(), 'Tristan, Merrow');
    assert.equal(await page.locator('blockquote p').textContent(), '“Nigel did a complete fit of an en-suite bathroom for us, including radiation, tiling, flooring, shower tray, glass window and toilet. We are very pleased with the result. Nigel communicated well and explained options along the way. Much recommended.”');
    assert.equal(await page.locator('#public-analytics').getAttribute('data-send-to-google'), 'false');
    assert.equal(await page.locator('header .navlinks').count(), 1);
    await page.evaluate(() => scrollTo({ top: 0, left: 0, behavior: "instant" }));
    if (evidence) {
      await page.screenshot({ path: join(evidence, `merrow-${name}.png`), fullPage: name === 'desktop' });
      if (name === 'desktop') await page.screenshot({ path: join(evidence, 'merrow-desktop-top.png') });
      if (name === 'desktop') {
        const images = {};
        for (const img of dimensions.images) {
          for (const source of new Set([img.source, img.defaultSource])) {
            const result = await context.request.get(source);
            images[source.replace(origin, '')] = `data:image/webp;base64,${(await result.body()).toString('base64')}`;
          }
        }
        // A shareable self-contained draft preview, with no analytics/network scripts.
        const html = await page.evaluate(images => {
          const doc = document.documentElement.cloneNode(true);
          for (const img of doc.querySelectorAll('main img')) {
            img.src = images[new URL(img.currentSrc || img.src, location.href).pathname] || images[img.getAttribute('src')];
            img.removeAttribute('srcset'); img.removeAttribute('sizes'); img.loading = 'eager';
          }
          for (const a of doc.querySelectorAll('a[href^="/project-images/"]')) {
            a.href = images[a.getAttribute('href')];
          }
          for (const script of doc.querySelectorAll('script:not([type="application/ld+json"])')) script.remove();
          doc.querySelector('#analytics-consent')?.remove();
          return '<!DOCTYPE html>\n' + doc.outerHTML;
        }, images);
        writeFileSync(join(evidence, 'merrow-case-study-preview.html'), html);
      }
    }
    diagnostics.layouts.push({ name, width, images: dimensions.images.length, overflow: false });
  }
  const sitemap = await (await context.request.get(origin + '/sitemap.xml')).text();
  assert(!sitemap.includes(path), 'Draft entered sitemap');
  assert.deepEqual(diagnostics.pageErrors, []);
  assert.deepEqual(diagnostics.externalRequests, []);
  if (evidence) writeFileSync(join(evidence, 'browser-validation.json'), JSON.stringify(diagnostics, null, 2) + '\n');
  console.log(JSON.stringify({ result: 'PASS', diagnostics }, null, 2));
} finally {
  if (browser) await browser.close();
  server.kill('SIGTERM');
}
