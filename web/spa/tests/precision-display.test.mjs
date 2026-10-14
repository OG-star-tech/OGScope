import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';

// Bundle the actual browser modules for this unit test. / 测试直接打包实际浏览器模块。
const built = await build({ stdin: { contents: 'export { formatArcsec } from "./src/shared/utils/solveDisplay"; export { drawSolveOverlay } from "./src/shared/drawOverlay";', resolveDir: fileURLToPath(new URL('..', import.meta.url)) }, bundle: true, format: 'esm', write: false });
const { formatArcsec, drawSolveOverlay } = await import('data:text/javascript;base64,' + Buffer.from(built.outputFiles[0].text).toString('base64'));
test('precision values use arcseconds with explicit conversion', () => {
  assert.equal(formatArcsec(0.14, 3600), '504.0″'); assert.equal(formatArcsec(10), '10.0″'); assert.equal(formatArcsec(0), '0.0″'); assert.equal(formatArcsec(null), '—'); assert.equal(formatArcsec(NaN), '—');
});
test('preview renders the supplied target distance without an independent calculation', () => {
  const texts = [];
  const ctx = new Proxy({ measureText: () => ({ width: 100 }), fillText: (text) => texts.push(text) }, { get: (obj, key) => key in obj ? obj[key] : () => {} });
  const canvas = { style: {}, getContext: () => ctx };
  drawSolveOverlay(canvas, { naturalWidth: 1280, naturalHeight: 720, clientWidth: 1280, clientHeight: 720 }, { overlay_ext: { polar_guide: { frame_center: { x: 640, y: 360 }, target: { x: 650, y: 350 }, angular_sep_deg: 0.14 } } }, { all: false, matched: false, pattern: false, rejected: false });
  assert.ok(texts.includes('Polar 504.0″')); assert.ok(!texts.join().includes('deg'));
});
