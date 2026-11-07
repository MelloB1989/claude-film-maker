#!/usr/bin/env bun
/// <reference types="bun" />
// The caption-band gate (gfx.caption_band_clear) for the WhatsApp v3 graphics, the same test as agent-12's
// films/explain-netflix/tools/bandcheck.py, with bun + ffmpeg (no numpy on the render Mac):
//
//   bun films/explain-whatsapp/tools/bandcheck.ts BLACK.mov OUT.json [--stride 3]
//
// --stride K: BLACK.mov holds only every Kth frame of each shot (stills at frames 0, K, 2K… of every shot, in film
// order, no lead): the quick form, from render.ts stills.
//
// BLACK.mov is films/explain-whatsapp-black rendered whole (half a frame of lead, every beat full frame, then the panel
// beats in their card; all over black, params.matte). Every 3rd frame of each shot is checked: it passes when nothing in
// rows y >= LIMIT (900 full, 918 panel) stands out of its surroundings by more than THR, on the high-passed brightness
// (the brightest channel minus its 41 px box blur), so a mark, an edge or a letter fails while the smooth bloom haze does
// not. Writes {"gate": {"gfx.caption_band_clear": {"value": 0|1, "where": ...}}, "shots": {...}}.
import edl from '../data/edl.json';

const argv = process.argv.slice(2);
const [src, outPath] = argv;
const si = argv.indexOf('--stride');
const STRIDE = si >= 0 ? Number(argv[si + 1]) : 0;
if (!src || !outPath) throw new Error('usage: bandcheck.ts BLACK.mov OUT.json');
const W = 1920, H = 1080, THR = 24, R = 20, TAIL = 12;

// the shots in film order: [id, first frame, frames, limit]
const rows: [string, number, number, number][] = [];
let f = STRIDE ? 0 : 1; // frame 0 is the lead (the whole film); none with --stride
const len = (n: number) => (STRIDE ? Math.ceil(n / STRIDE) : n);
for (const s of edl.shots) rows.push([s.gfx, f, len(s.frames + TAIL), 900]), (f += len(s.frames + TAIL));
for (const s of edl.shots.filter((x) => x.kind === 'panel')) rows.push([`${s.gfx}_panel`, f, len(s.frames + TAIL), 918]), (f += len(s.frames + TAIL));

const dec = Bun.spawn(['ffmpeg', '-v', 'error', '-i', src, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], { stdout: 'pipe', stderr: 'inherit' });
const reader = dec.stdout.getReader();
let buf = new Uint8Array(0);
async function next(): Promise<Uint8Array | null> {
  const n = W * H * 3;
  while (buf.length < n) {
    const { value, done } = await reader.read();
    if (done) return null;
    const nb = new Uint8Array(buf.length + value.length);
    nb.set(buf);
    nb.set(value, buf.length);
    buf = nb;
  }
  const fr = buf.slice(0, n);
  buf = buf.slice(n);
  return fr;
}

/** The worst high-passed brightness in rows >= lim (and where), for one rgb24 frame. */
function worst(px: Uint8Array, lim: number): { v: number; x: number; y: number } {
  const y0 = Math.max(0, lim - R - 1);
  const h = H - y0, w = W;
  const L = new Float64Array(h * w);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const i = ((y + y0) * W + x) * 3;
    L[y * w + x] = Math.max(px[i]!, px[i + 1]!, px[i + 2]!);
  }
  // integral image with clamped edges: S over the padded grid
  const pw = w + 2 * (R + 1), ph = h + 2 * (R + 1);
  const S = new Float64Array((pw + 1) * (ph + 1));
  for (let y = 0; y < ph; y++) {
    let row = 0;
    const sy = Math.min(h - 1, Math.max(0, y - (R + 1)));
    for (let x = 0; x < pw; x++) {
      const sx = Math.min(w - 1, Math.max(0, x - (R + 1)));
      row += L[sy * w + sx]!;
      S[(y + 1) * (pw + 1) + (x + 1)] = S[y * (pw + 1) + (x + 1)]! + row;
    }
  }
  const k = 2 * R + 1;
  let best = { v: 0, x: 0, y: 0 };
  for (let y = lim - y0; y < h; y++) for (let x = 0; x < w; x++) {
    // the box centred on (x, y): padded coords (x + R + 1, y + R + 1), so it spans [x + 1, x + 1 + k)
    const ax = x + 1, ay = y + 1, bx = ax + k, by = ay + k;
    const sum = S[by * (pw + 1) + bx]! - S[ay * (pw + 1) + bx]! - S[by * (pw + 1) + ax]! + S[ay * (pw + 1) + ax]!;
    const v = L[y * w + x]! - sum / (k * k);
    if (v > best.v) best = { v, x, y: y + y0 };
  }
  return best;
}

const shots: Record<string, { frames: number; fail: number[]; max: number; at?: [number, number] }> = {};
for (const [id] of rows) shots[id] = { frames: 0, fail: [], max: 0 };
let frame = 0;
for (;;) {
  const fr = await next();
  if (!fr) break;
  const row = rows.find(([, a, n]) => frame >= a && frame < a + n);
  if (row && (STRIDE || (frame - row[1]) % 3 === 0)) {
    const [id, a, , lim] = row;
    const b = worst(fr, lim), r = shots[id]!;
    r.frames++;
    if (b.v > r.max) (r.max = Math.round(b.v)), (r.at = [b.x, b.y]);
    if (b.v > THR) r.fail.push((frame - a) * (STRIDE || 1));
  }
  frame++;
}
const bad = Object.entries(shots).filter(([, r]) => r.fail.length);
const out = { gate: { 'gfx.caption_band_clear': { value: bad.length ? 0 : 1, where: bad.map(([id, r]) => `${id}: frames ${r.fail.join(',')} (max ${r.max} at ${r.at})`) } }, shots };
await Bun.write(outPath, JSON.stringify(out, null, 1));
for (const [id, r] of Object.entries(shots)) console.log(`${id.padEnd(14)} ${r.frames} checked, max ${r.max}${r.at ? ` at ${r.at}` : ''}${r.fail.length ? `  FAIL ${r.fail.length}` : ''}`);
console.log(`gfx.caption_band_clear = ${out.gate['gfx.caption_band_clear'].value}`);
