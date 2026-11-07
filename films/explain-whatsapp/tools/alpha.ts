#!/usr/bin/env bun
// Straight-alpha ProRes 4444 from a panel shot rendered twice, over black and over grey (films/explain-whatsapp-panel:
// <id>_k and <id>_g), with nothing but ffmpeg and bun (no numpy on the render Mac):
//
//   bun films/explain-whatsapp/tools/alpha.ts BLACK.mov GREY.mov OUT.mov [--grey 128] [--png DIR]
//
// Over black a pixel shows its premultiplied colour B; over grey (level k/255) it shows B + (1 - a) k, so the coverage
// is a = 1 - mean(G - B) / k. Light that a glow or the bloom added has no coverage of its own: it keeps max(a, max(B)),
// which composites close to the 'add' it was drawn with (as agent-12's alpha.py). The colour is B / a, straight.
// ffmpeg decodes both to raw rgb24 on pipes, this computes rgba frame by frame, ffmpeg encodes ProRes 4444 (and PNGs).
const argv = process.argv.slice(2);
const [black, grey, out] = argv;
if (!black || !grey || !out) throw new Error('usage: alpha.ts BLACK.mov GREY.mov OUT.mov [--grey 128] [--png DIR]');
const opt = (k: string) => { const i = argv.indexOf(`--${k}`); return i >= 0 ? argv[i + 1] : undefined; };
const K = Number(opt('grey') ?? 128) / 255;
const png = opt('png');
const W = 1920, H = 1080, N = W * H;

function decoder(path: string) {
  const p = Bun.spawn(['ffmpeg', '-v', 'error', '-i', path, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], { stdout: 'pipe', stderr: 'inherit' });
  const reader = p.stdout.getReader();
  let buf = new Uint8Array(0);
  return async function next(): Promise<Uint8Array | null> {
    while (buf.length < N * 3) {
      const { value, done } = await reader.read();
      if (done) return null;
      const nb = new Uint8Array(buf.length + value.length);
      nb.set(buf);
      nb.set(value, buf.length);
      buf = nb;
    }
    const f = buf.slice(0, N * 3);
    buf = buf.slice(N * 3);
    return f;
  };
}

const enc = Bun.spawn(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', `${W}x${H}`, '-r', '24', '-i', '-',
  '-c:v', 'prores_ks', '-profile:v', '4', '-pix_fmt', 'yuva444p10le', '-alpha_bits', '16', '-vendor', 'apl0', out], { stdin: 'pipe', stderr: 'inherit' });
const pngEnc = png
  ? Bun.spawn(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', `${W}x${H}`, '-r', '24', '-i', '-', `${png}/%05d.png`], { stdin: 'pipe', stderr: 'inherit' })
  : null;
const nb = decoder(black), ng = decoder(grey);
const rgba = new Uint8Array(N * 4);
let frames = 0, maxOutside = 0;
for (;;) {
  const [B, G] = await Promise.all([nb(), ng()]);
  if (!B || !G) {
    if (B || G) throw new Error(`alpha.ts: ${black} and ${grey} differ in length (at frame ${frames})`);
    break;
  }
  for (let i = 0, j = 0, o = 0; i < N; i++, j += 3, o += 4) {
    const br = B[j]! / 255, bg = B[j + 1]! / 255, bb = B[j + 2]! / 255;
    const d = ((G[j]! - B[j]!) + (G[j + 1]! - B[j + 1]!) + (G[j + 2]! - B[j + 2]!)) / (3 * 255);
    let a = 1 - d / K;
    const mb = Math.max(br, bg, bb);
    if (mb > a) a = mb;
    if (a > 1) a = 1;
    if (a < 2 / 255) a = 0;
    if (a > 0) {
      rgba[o] = Math.min(255, Math.round((br / a) * 255));
      rgba[o + 1] = Math.min(255, Math.round((bg / a) * 255));
      rgba[o + 2] = Math.min(255, Math.round((bb / a) * 255));
    } else rgba[o] = rgba[o + 1] = rgba[o + 2] = 0;
    rgba[o + 3] = Math.round(a * 255);
  }
  // a check: the frame's top-left corner is far outside the panel box, so it should stay (nearly) clear
  for (let y = 0; y < 100; y += 10) for (let x = 0; x < 400; x += 10) maxOutside = Math.max(maxOutside, rgba[(y * W + x) * 4 + 3]!);
  enc.stdin.write(rgba);
  pngEnc?.stdin.write(rgba);
  frames++;
}
enc.stdin.end();
pngEnc?.stdin.end();
await enc.exited;
await pngEnc?.exited;
console.log(`${out}: ${frames} frames, max alpha in the far corner ${maxOutside}`);
