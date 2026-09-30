// What only Chrome can show: how Canvas2D sets the film's type, and what a 2D context keeps from one frame to the next.
// gl.ts and type.ts are bundled (Bun.build) into a blank page served from memory, and the fonts load off disk through
// the page's own loadFonts(), as the film's do. Needs Google Chrome, as scripts/render.ts does.
import { afterAll, beforeAll, expect, test } from 'bun:test';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { chromium, type Browser, type Page } from 'playwright-core';

const ORIGIN = 'http://film.test';
const FONTS = path.resolve(import.meta.dir, '../../public/fonts');
let browser: Browser;
let page: Page;

beforeAll(async () => {
  const dir = mkdtempSync(path.join(tmpdir(), 'film-chrome-'));
  const entry = path.join(dir, 'entry.ts');
  const mod = (f: string) => JSON.stringify(path.join(import.meta.dir, f));
  writeFileSync(entry, `import * as gl from ${mod('gl.ts')};\nimport * as type from ${mod('type.ts')};\n(window as any).__t = { gl, type };\n`);
  const built = await Bun.build({ entrypoints: [entry], target: 'browser', format: 'esm' });
  rmSync(dir, { recursive: true, force: true });
  if (!built.success) throw new AggregateError(built.logs, 'bundling gl.ts and type.ts failed');
  const code = await built.outputs[0]!.text();
  browser = await chromium.launch({ channel: 'chrome', headless: true });
  page = await browser.newPage();
  await page.route(`${ORIGIN}/**`, (route) => {
    const p = new URL(route.request().url()).pathname;
    if (p.startsWith('/fonts/')) return route.fulfill({ body: readFileSync(path.join(FONTS, path.basename(p))), contentType: 'font/ttf' });
    return route.fulfill({ body: '<!doctype html><meta charset="utf-8"><body></body>', contentType: 'text/html' });
  });
  await page.goto(`${ORIGIN}/`);
  await page.addScriptTag({ content: code, type: 'module' });
  await page.waitForFunction(() => (window as any).__t);
  await page.evaluate(() => (window as any).__t.type.loadFonts());
}, 60000);

afterAll(async () => {
  await browser?.close();
});

test('the mono faces set `->`, `--` and `//` as their glyphs apart: Chrome takes the faces\' ligatures off', async () => {
  const r = await page.evaluate(async () => {
    const { gl, type } = (window as any).__t;
    /** `s` drawn whole on a Layer2D (as a scene's fillText would), against its glyphs drawn one by one on the grid. */
    const compare = (family: string, s: string) => {
      const draw = (whole: boolean) => {
        const L = new gl.Layer2D(420, 120, 1), c = L.ctx as CanvasRenderingContext2D;
        L.clear('#000');
        c.font = type.font(family, 80);
        c.fillStyle = '#fff';
        if (whole) c.fillText(s, 20, 90);
        else {
          let x = 20;
          for (const ch of Array.from(s)) (c.fillText(ch, x, 90), (x += c.measureText(ch).width));
        }
        return { px: c.getImageData(0, 0, 420, 120).data, width: c.measureText(s).width, apart: Array.from(s).reduce((w, ch) => w + c.measureText(ch).width, 0) };
      };
      const a = draw(true), b = draw(false);
      let differ = 0, ink = 0;
      for (let i = 0; i < a.px.length; i += 4) {
        if (a.px[i] !== b.px[i]) differ++;
        if (b.px[i]! > 0) ink++;
      }
      return { family, s, differ, ink, width: a.width, apart: a.apart };
    };
    const mono = type.fontFamilies().filter((f: string) => f.startsWith('JBMono'));
    const out = mono.flatMap((f: string) => ['->', '--', '//', '--scope', '!=', '=='].map((s) => compare(f, s)));
    // the control: the same face without its descriptors joins them, so the check can see a ligature
    const buf = await (await fetch('fonts/JetBrainsMono-400.ttf')).arrayBuffer();
    const lig = new FontFace('JBMono-400-ligatures', buf);
    await lig.load();
    document.fonts.add(lig);
    return { out, control: ['->', '--', '//'].map((s) => compare('JBMono-400-ligatures', s)) };
  });
  expect(r.out.map((x: { family: string }) => x.family).sort()).toContain('JBMono-400');
  for (const x of r.out) {
    expect({ ...x, differ: x.differ }).toEqual({ ...x, differ: 0 });
    expect(x.ink).toBeGreaterThan(100); // something was drawn
    expect(x.width).toBeCloseTo(x.apart, 3);
  }
  for (const x of r.control) expect(x.differ).toBeGreaterThan(50);
});

test('Layer2D.clear() starts the frame from a fresh context: no pixels, no state, no path, no saved state', async () => {
  const r = await page.evaluate(() => {
    const { gl } = (window as any).__t;
    const snap = (c: CanvasRenderingContext2D) => {
      const m = c.getTransform();
      return {
        font: c.font, textAlign: c.textAlign, textBaseline: c.textBaseline, direction: c.direction, letterSpacing: c.letterSpacing,
        wordSpacing: c.wordSpacing, fontKerning: c.fontKerning, fillStyle: c.fillStyle, strokeStyle: c.strokeStyle,
        lineWidth: c.lineWidth, lineCap: c.lineCap, lineJoin: c.lineJoin, miterLimit: c.miterLimit, lineDash: c.getLineDash(),
        lineDashOffset: c.lineDashOffset, shadowColor: c.shadowColor, shadowBlur: c.shadowBlur, shadowOffsetX: c.shadowOffsetX,
        shadowOffsetY: c.shadowOffsetY, globalAlpha: c.globalAlpha, globalCompositeOperation: c.globalCompositeOperation,
        filter: c.filter, imageSmoothingEnabled: c.imageSmoothingEnabled, transform: [m.a, m.b, m.c, m.d, m.e, m.f],
      };
    };
    const used = new gl.Layer2D(40, 20, 2), fresh = new gl.Layer2D(40, 20, 2), freshState = snap(fresh.ctx);
    const c = used.ctx as CanvasRenderingContext2D;
    // a frame that changes everything and leaves a save() unrestored and a path open
    c.save();
    c.translate(3, 4);
    c.scale(2, 2);
    Object.assign(c, {
      font: '31px serif', textAlign: 'right', textBaseline: 'top', direction: 'rtl', letterSpacing: '3px', wordSpacing: '2px',
      fontKerning: 'none', fillStyle: '#123456', strokeStyle: '#654321', lineWidth: 7, lineCap: 'round', lineJoin: 'bevel',
      miterLimit: 3, lineDashOffset: 1, shadowColor: '#ff0000', shadowBlur: 3, shadowOffsetX: 5, shadowOffsetY: 6,
      globalAlpha: 0.5, globalCompositeOperation: 'multiply', filter: 'blur(2px)', imageSmoothingEnabled: false,
    });
    c.setLineDash([4, 2]);
    c.fillRect(0, 0, 40, 20);
    c.beginPath();
    c.rect(1, 1, 5, 5);
    used.clear();
    const state = snap(c), inPath = c.isPointInPath(15, 15);
    const blank = c.getImageData(0, 0, 80, 40).data.every((v) => v === 0);
    c.restore(); // the frame before's save() is gone with it: nothing to restore
    const restored = snap(c);
    // the base scale stays: a logical px is 2x2 backing px
    c.fillStyle = '#fff';
    c.fillRect(1, 1, 1, 1);
    const px = Array.from(c.getImageData(0, 0, 4, 4).data.filter((_, i) => i % 4 === 3));
    // a translucent clear colour is the frame's colour, not mixed over the frame before
    used.ctx.fillStyle = '#fff';
    used.ctx.fillRect(0, 0, 40, 20);
    used.clear('rgba(255, 0, 0, 0.5)');
    fresh.clear('rgba(255, 0, 0, 0.5)');
    const tinted = [Array.from(used.ctx.getImageData(5, 5, 1, 1).data), Array.from(fresh.ctx.getImageData(5, 5, 1, 1).data)];
    return { state, fresh: freshState, inPath, blank, restored, px, tinted };
  });
  expect(r.state).toEqual(r.fresh);
  expect(r.inPath).toBe(false);
  expect(r.blank).toBe(true);
  expect(r.restored).toEqual(r.fresh);
  expect(r.px).toEqual([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 255, 255, 0, 0, 255, 255]);
  expect(r.tinted[0]).toEqual(r.tinted[1]);
});
