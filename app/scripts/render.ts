#!/usr/bin/env bun
// Offline renderer. Drives the app in headless Chrome (?export=1) and either
//   stills:  bun scripts/render.ts stills --t 1.5,23,40.2 [--only id1,id2] [--out dir]   (warns of a time half way between two
//            frames, t·30 within 0.1 of n + 0.5: its shutter straddles both frames' states)
//   sheet:   bun scripts/render.ts sheet [--from 0 --to 10] [--n 12] [--cols 4] [--only ids] [--out file.png]   (or --times a,b,c | --cuts)
//   perf:    bun scripts/render.ts perf [--from 0 --to 5] [--only ids] [--samples 1] [--shutter 0.5]   (avg ms per frame incl. GPU sync and the export's pixel readback)
//   video:   bun scripts/render.ts video [--only id] [--from 0] [--to <duration>] [--fps 30] [--crf 16] [--x264 aq-mode=3] [--samples 1] [--shutter 0.5] [--out ../out/gitloom.mp4, or ../out/<only|module>.mp4] [--noaudio]
//            --samples N averages N sub-frames per frame over shutter×(1/fps): motion blur + temporal AA;
//            --samples auto picks the count per frame (4, 12, 36, 108 or 324, see Engine.render)
//            Without --out, a range given with --from/--to is named for it too, <name>_<from>-<to>.mp4 (out/gitloom_5.5-7.mp4):
//            only the whole film is out/gitloom.mp4, and only a scene's whole window out/<id>.mp4.
//            A scene error (init, a missing plate frame, a throw in render) or a lost WebGL context fails the export: nothing
//            is renamed to --out, `<out>.progress` reads "FAILED: <reason>", and `<out>.partial` plays up to the failure.
//   --proxies (all modes): a plate frame whose EXR is missing composites its 960x540 proxy (a draft, warned once);
//            without it the missing EXR fails the export.
//   --only ID (sheet, perf, video) with ONE scene id and neither --from nor --to: exactly the frames that scene owns,
//            frame f being the scene's when f/fps falls in its window [start, end) (--only her: frames 469…684 at
//            30 fps, 216 frames). The sheet's first and last stills are then its first and last frames, saved to
//            out/sheets/sheet_<id>.png by default. With several ids, or --from/--to given, the window is as given.
//            (--only loads just those scenes: a frame of any other scene renders as red fill.)
//   --scale N (all modes): render at N× the 1920x1080 layout (--scale 2 = true 3840x2160); stills are then saved
//            full-res from the pixel buffer, videos are encoded at the physical size.
//   --module NAME (all modes): play scenes/NAME.ts alone over [0, duration] instead of the film's timeline (a dev
//            harness such as _stagetest; ?module= in main.ts). --only is ignored then.
//   --allow-software (all modes, `gpu` aside): the hardware check. The engine's unmasked renderer string is printed once at
//            startup, and a software one (SwiftShader, llvmpipe, Software, Basic Render) fails the run unless this is given.
//            Under heavy GPU load (a Blender render beside this) Chrome can fall back to SwiftShader without a word, and what it
//            renders differs from the GPU's (grain hash noise, edges: 2-3 levels on average, up to 133 in a still). A video reads
//            the string again after its last frame and fails if it changed; a still or a stream fails if the page saw its WebGL
//            context lost.
//   --transition FILE (stills, video, sheet): review transitions/FILE.ts (a dev probe, _probe-*.ts, too) as the film's only
//            transition, loading only its two scenes (unless --only says otherwise). Its window [start, end) around the cut
//            sets the defaults: video renders [start − 1, end + 1] (cut ± 1 for a 'cut'), whole frames, to
//            out/transitions/FILE.mp4; sheet shows every frame of the window ±3 frames (a 'cut': frames F − 3 … F + 2) to
//            out/transitions/FILE-sheet.png; stills render --frames (default -3,-2,-1,0,1,2), or --t, to
//            out/transitions/FILE/. --from/--to/--times/--out override them.
//   --frames K,K… (stills, with --transition): film frames relative to B's first frame F = ceil(cut·30), saved as
//            f<±K>_<frame>.png.
//   --test-lose-context N (video, test only): the page loses its WebGL context (WEBGL_lose_context) once frame N has been
//            sent (frames as --from/--to count them: at --fps from 0). The export must fail: exit 1, "FAILED: the WebGL
//            context was lost…" in <out>.progress, <out>.partial left, nothing at --out.
// Uses the Vite dev server at --url (default http://localhost:5173); starts a private one if unreachable.
import { chromium, type Page } from 'playwright-core';
import { mkdirSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { ownedFrames, straddledFrames } from '../src/engine/engine';
import { isSoftwareRenderer } from '../src/engine/gpu';
import { VO } from '../src/engine/vo';
import { specOf, type TransitionModule } from '../src/engine/transition';

const argv = process.argv.slice(2);
const mode = argv[0] ?? 'stills';
const opt = (k: string, d?: string) => { const i = argv.indexOf(`--${k}`); return i >= 0 ? argv[i + 1] : d; };
const flag = (k: string) => argv.includes(`--${k}`);
const APP = path.resolve(import.meta.dir, '..');
const SCALE = Math.max(1, Math.round(+opt('scale', '1')!));
const OW = 1920 * SCALE, OH = 1080 * SCALE; // output size
// --samples N (fixed) or --samples auto [--min-samples 4] [--max-samples 324] [--tol 3] (adaptive, see Engine.render)
const SAMPLES = opt('samples', '1') === 'auto'
  ? { min: +opt('min-samples', '4')!, max: +opt('max-samples', '324')!, tol: +opt('tol', '3')! }
  : +opt('samples', '1')!;
const hist = (h: Record<string, number>) => Object.entries(h).sort((a, b) => +a[0] - +b[0]).map(([k, v]) => `${k}:${v}`).join(' ');
const ROOT = path.resolve(APP, '..');
const LOSE_AFTER = flag('test-lose-context') ? +opt('test-lose-context')! : undefined; // (video, test only)
if (LOSE_AFTER !== undefined && !Number.isInteger(LOSE_AFTER)) throw new Error('--test-lose-context takes a frame number');
// --transition FILE: its spec, read here for the two scenes to load (the page validates it and reports its window)
const TRANSITION = opt('transition');
if (TRANSITION !== undefined && !/^[\w-]+$/.test(TRANSITION)) throw new Error(`--transition takes a transition file name (transitions/<name>.ts), got '${TRANSITION}'`);
const TR_SPEC = TRANSITION ? specOf(await import(path.join(APP, 'src/transitions', `${TRANSITION}.ts`)) as TransitionModule, new VO(await Bun.file(path.join(ROOT, 'data/vo.json')).json())) : null;
/** A transition in play on the page (main.ts __film.transitions). */
interface PageTransition { id: string; cut: number; start: number; end: number; kind: string; from: string; to: string }

async function reachable(url: string) {
  try { const r = await fetch(url, { signal: AbortSignal.timeout(1500) }); return r.ok; } catch { return false; }
}

async function ensureServer(): Promise<{ url: string; stop: () => void }> {
  const url = opt('url', 'http://localhost:5173')!;
  if (await reachable(url)) return { url, stop: () => {} };
  const port = 5300 + Math.floor(Math.random() * 500);
  // no live reload: a file saved mid-render must not reload the page
  const proc = Bun.spawn(['bunx', 'vite', '--port', String(port), '--strictPort'], { cwd: APP, stdout: 'ignore', stderr: 'ignore', env: { ...process.env, FILM_NO_HMR: '1' } });
  const u = `http://localhost:${port}`;
  for (let i = 0; i < 100 && !(await reachable(u)); i++) await Bun.sleep(100);
  return { url: u, stop: () => proc.kill() };
}

async function openPage(url: string) {
  const browser = await chromium.launch({
    channel: 'chrome',
    headless: !flag('headed'),
    args: ['--use-angle=metal', '--enable-gpu-rasterization', '--ignore-gpu-blocklist', '--disable-background-timer-throttling', '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows'],
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
    const logs: string[] = [];
    page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') logs.push(`[${m.type()}] ${m.text()}`); });
    page.on('pageerror', (e) => logs.push(`[pageerror] ${e.message}`));
    const only = opt('only') ?? (TR_SPEC ? `${TR_SPEC.from},${TR_SPEC.to}` : undefined), module = opt('module');
    if (module && !/^[\w-]+$/.test(module)) throw new Error(`--module takes a scene file name (scenes/<name>.ts), got '${module}'`);
    const sel = (module ? `&module=${module}` : only ? `&only=${only}` : '') + (TRANSITION && !module ? `&transition=${TRANSITION}` : '');
    await page.goto(`${url}/?export=1${sel}${SCALE !== 1 ? `&scale=${SCALE}` : ''}${flag('proxies') ? '&proxies=1' : ''}`);
    await page.waitForFunction(() => (window as any).__film?.ready || (window as any).__film?.error, null, { timeout: 120000 });
    const err = await page.evaluate(() => (window as any).__film.error);
    if (err) throw new Error(`app failed to boot:\n${err}\n${logs.join('\n')}`);
    const size: [number, number] = await page.evaluate(() => [(window as any).__film.width ?? 1920, (window as any).__film.height ?? 1080]);
    if (size[0] !== OW || size[1] !== OH) throw new Error(`app renders ${size[0]}x${size[1]}, expected ${OW}x${OH} (--scale ${SCALE})`);
    const sceneErrors: string[] = await page.evaluate(() => (window as any).__film.errors);
    if (sceneErrors.length) console.error('SCENE ERRORS:\n' + sceneErrors.join('\n'));
    return { browser, page, logs };
  } catch (e) {
    await browser.close();
    throw e;
  }
}

/**
 * The hardware check, in every mode but `gpu`: prints the renderer string once, and fails the run when it is a software
 * one (isSoftwareRenderer) unless --allow-software.
 */
function checkRenderer(gpu: string) {
  const soft = isSoftwareRenderer(gpu);
  if (soft && !flag('allow-software')) {
    throw new Error(`WebGL runs on a software renderer (${gpu}), not the GPU: its frames differ from the GPU's in grain hash noise and edges. Chrome falls back to it when the GPU is overloaded or lost (a Blender render beside this one?): free the GPU and run again, or pass --allow-software to render a draft anyway.`);
  }
  console.log(`renderer: ${gpu}${soft ? '  (software, --allow-software)' : ''}`);
}

/**
 * With --only and ONE scene id, and neither --from nor --to (nor --module): the frames that scene owns at fps
 * (ownedFrames), else null.
 */
async function sceneFrames(page: Page, fps: number): Promise<{ id: string; first: number; last: number } | null> {
  const id = opt('only');
  if (!id || id.includes(',') || opt('module') || flag('from') || flag('to')) return null;
  const tl: { id: string; start: number; end: number }[] = await page.evaluate(() => (window as any).__film.timeline);
  const e = tl.find((x) => x.id === id);
  if (!e) throw new Error(`--only ${id}: no such scene (the timeline has ${tl.map((x) => x.id).join(', ')})`);
  const { first, last } = ownedFrames(e, fps);
  if (last < first) throw new Error(`--only ${id}: its window [${e.start}, ${e.end}) holds no frame at ${fps} fps`);
  console.log(`${id}: frames ${first}…${last} (${last - first + 1}) at ${fps} fps, its window [${e.start}, ${e.end})`);
  return { id, first, last };
}

async function stills(page: Page, times: number[], outDir: string, names?: string[]) {
  mkdirSync(outDir, { recursive: true });
  const files: string[] = [];
  for (const [i, t] of times.entries()) {
    // a time half way between two frames blends both frames' states across its shutter (an export never renders one)
    const two = straddledFrames(t, 30);
    if (two) console.warn(`WARNING t=${t}: ${(t * 30).toFixed(2)} frames, half way between frames ${two[0]} and ${two[1]}: its shutter straddles both frames' states, which no export renders (frame times: ${(two[0] / 30).toFixed(4)}, ${(two[1] / 30).toFixed(4)})`);
    const k: number = await page.evaluate(([t, s, sh]) => (window as any).__film.still(t, s, sh), [t, SAMPLES, +opt('shutter', '0.5')!] as const);
    const f = path.join(outDir, names?.[i] ?? `f_${t.toFixed(2).padStart(7, '0')}.png`);
    if (typeof SAMPLES !== 'number') console.log(`t=${t}: ${k} sub-frames`);
    // at scale > 1 the canvas is shown downscaled on the page: save the full-res pixel buffer instead
    if (SCALE !== 1) await Bun.write(f, Buffer.from(await page.evaluate(() => (window as any).__film.png()), 'base64'));
    else {
      const shot = await page.screenshot({ clip: { x: 0, y: 0, width: 1920, height: 1080 } });
      await page.evaluate(() => (window as any).__film.assertLive()); // a canvas whose context was lost since the still is not the frame: no file
      await Bun.write(f, shot);
    }
    files.push(f);
  }
  return files;
}

async function sheet(page: Page, times: number[], cols: number, out: string) {
  const dataUrl: string = await page.evaluate(async ({ times, cols }) => {
    const P = (window as any).__film;
    const cw = 480, ch = 270, pad = 4, lab = 18;
    const rows = Math.ceil(times.length / cols);
    const cv = document.createElement('canvas');
    cv.width = cols * (cw + pad) + pad; cv.height = rows * (ch + lab + pad) + pad;
    const c = cv.getContext('2d')!;
    c.fillStyle = '#222'; c.fillRect(0, 0, cv.width, cv.height);
    const src = document.getElementById('c') as HTMLCanvasElement;
    for (let i = 0; i < times.length; i++) {
      const t = times[i]!;
      await P.still(t); // (after the frame's scenes have prepared it: plates)
      const x = pad + (i % cols) * (cw + pad), y = pad + Math.floor(i / cols) * (ch + lab + pad);
      c.drawImage(src, x, y + lab, cw, ch);
      c.fillStyle = '#ddd'; c.font = '13px monospace'; c.fillText(`${t.toFixed(2)}s`, x + 2, y + 13);
    }
    return cv.toDataURL('image/png');
  }, { times, cols });
  mkdirSync(path.dirname(out), { recursive: true });
  await Bun.write(out, Buffer.from(dataUrl.split(',')[1]!, 'base64'));
}

const clock = (s: number) => `${Math.floor(s / 60)}m${String(Math.round(s % 60)).padStart(2, '0')}s`;

async function video(page: Page, from: number, to: number, fps: number, out: string, gpu: string) {
  mkdirSync(path.dirname(out), { recursive: true });
  // Encoded under a temporary name and renamed only when ffmpeg has finished and the page reports no scene error, so
  // a failed or killed export never leaves a file at `out`; `<out>.progress` says how far a running one has got, and
  // "FAILED: <reason>" once one has failed. The file itself grows in bursts minutes apart (x264's lookahead holds ~40
  // frames, and a motion-blurred frame can take seconds), so its size is no guide.
  const part = `${out}.partial`, progress = `${out}.progress`;
  const crf = opt('crf', '16')!;
  const audio = path.join(ROOT, 'audio/mix/mix.wav');
  const args = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', `${OW}x${OH}`, '-r', String(fps), '-i', 'pipe:0'];
  if (!flag('noaudio')) args.push('-ss', String(from), '-t', String(to - from), '-i', audio);
  // Frames are sRGB (toSRGB in the final pass): convert with the BT.709 matrix and tag the stream,
  // otherwise ffmpeg converts with BT.601 while players and YouTube decode untagged HD as BT.709.
  // scale tags the matrix and range; primaries and transfer need setparams (the -color_* output flags don't reach the stream).
  args.push('-vf', 'vflip,scale=out_color_matrix=bt709,setparams=color_primaries=bt709:color_trc=bt709', '-c:v', 'libx264', '-preset', opt('preset', 'slow')!, '-crf', crf, '-pix_fmt', 'yuv420p', '-tune', 'grain', '-x264-params', opt('x264', 'aq-mode=3')!);
  if (!flag('noaudio')) args.push('-c:a', 'aac', '-b:a', '320k', '-shortest');
  args.push('-movflags', '+faststart', '-f', path.extname(out).toLowerCase() === '.mov' ? 'mov' : 'mp4', part);
  const ff = Bun.spawn(args, { stdin: 'pipe', stdout: 'inherit', stderr: 'inherit' });
  let frames = 0, failed = false, quit = false;
  void ff.exited.then(() => (quit = true));
  const total = Math.round(to * fps) - Math.round(from * fps);
  const t0 = performance.now();
  let noted = -Infinity;
  const note = () => {
    const el = (performance.now() - t0) / 1000, rate = frames / el;
    const line = `${frames}/${total} frames  ${rate.toFixed(2)} fps  eta ${clock((total - frames) / rate)}`;
    process.stdout.write(`\r${line}   `);
    if (performance.now() - noted >= 1000 || frames === total) {
      writeFileSync(progress, `${line}  (${clock(el)} elapsed, encoding to ${path.basename(part)})\n`);
      noted = performance.now();
    }
  };
  writeFileSync(progress, `0/${total} frames  starting\n`);
  const server = Bun.serve({
    port: 0,
    fetch(req, srv) { return srv.upgrade(req) ? undefined : new Response('ws only', { status: 400 }); },
    websocket: {
      maxPayloadLength: Math.max(64 * 1024 * 1024, OW * OH * 4 + 1024),
      async message(ws, msg) {
        if (failed) return;
        try {
          ff.stdin.write(msg as Uint8Array);
          await ff.stdin.flush();
        } catch {
          ws.close(); // ffmpeg has quit (its exit code says why): the page stops rendering
          return;
        }
        frames++;
        ws.send(String(frames)); // ack: the page keeps at most a few frames ahead of ffmpeg (bounded memory at 4K)
        note();
      },
    },
  });
  try {
    // (rejects on a scene error: the page sends no frame after it)
    const used: Record<string, number> = await page.evaluate((o) => (window as any).__film.stream(o), { from, to, fps, ws: `ws://localhost:${server.port}`, samples: SAMPLES, shutter: +opt('shutter', '0.5')!, inflight: 4, loseContextAfter: LOSE_AFTER });
    // the GPU this export began on rendered its last frame too (a context restored on a software renderer already failed the
    // stream; this catches a change that did not): reading the string from a lost context throws
    const end: string = await page.evaluate(() => (window as any).__film.renderer());
    if (end !== gpu) throw new Error(`the renderer changed during the export: it began on ${gpu} and ended on ${end}`);
    // wait for all frames to arrive (or ffmpeg to quit)
    while (frames < total && !quit) await Bun.sleep(20);
    ff.stdin.end();
    const code = await ff.exited;
    if (code !== 0) throw new Error(`ffmpeg exited ${code}`);
    // a scene error the page recorded without failing the stream still keeps the file from its name
    const errors: string[] = await page.evaluate(() => (window as any).__film.errors);
    if (errors.length) throw new Error(`the page recorded scene errors:\n${errors.join('\n')}`);
    renameSync(part, out);
    rmSync(progress, { force: true });
    console.log(`\nwrote ${out} (${frames} frames in ${((performance.now() - t0) / 1000).toFixed(1)}s)`);
    console.log(`sub-frames per frame (count:frames): ${hist(used)}`);
  } catch (e) {
    failed = true;
    // ffmpeg finishes what it has (the partial plays up to the failure), and the file keeps its .partial name
    try {
      ff.stdin.end();
    } catch {
      // already closed
    }
    const code = await ff.exited;
    let reason = String((e as Error)?.message ?? e).split('\n')[0]!.replace(/^(page\.)?evaluate: (Error: )?/, '');
    if (code !== 0 && !reason.startsWith('ffmpeg')) reason += ` (ffmpeg exited ${code})`;
    writeFileSync(progress, `FAILED: ${reason}\n${frames}/${total} frames encoded to ${path.basename(part)}, not renamed to ${path.basename(out)}\n`);
    console.error(`\nFAILED: ${reason}\n(${frames}/${total} frames are in ${part}; see ${progress})`);
    throw e;
  } finally {
    server.stop(true);
  }
}

const { url, stop } = await ensureServer();
let session: Awaited<ReturnType<typeof openPage>> | undefined;
try {
  session = await openPage(url);
  const { page } = session;
  // the engine's own context, the one that renders: Chrome under GPU load can fall back to a software renderer
  const gpu: string = await page.evaluate(() => (window as any).__film.renderer());
  if (mode !== 'gpu') checkRenderer(gpu);
  // --transition: the one transition the page plays, and the frames around it
  let tr: PageTransition | null = null;
  if (TRANSITION) {
    const trs: PageTransition[] = await page.evaluate(() => (window as any).__film.transitions);
    tr = trs[0] ?? null;
    if (!tr) throw new Error(`--transition ${TRANSITION}: the page plays no transition`);
    console.log(`transition ${tr.id} (${tr.kind}): cut ${tr.cut}, window [${tr.start}, ${tr.end}), B's first frame ${ownedFrames({ start: tr.cut, end: tr.cut }, 30).first}`);
  }
  if (mode === 'gpu') {
    console.log(gpu);
  } else if (mode === 'stills') {
    let times = (opt('t') ?? '0').split(',').map(Number), names: string[] | undefined;
    if (tr && !opt('t')) {
      // film frames relative to B's first frame F
      const F = ownedFrames({ start: tr.cut, end: tr.cut }, 30).first;
      const ks = (opt('frames') ?? '-3,-2,-1,0,1,2').split(',').map(Number);
      if (ks.some((k) => !Number.isInteger(k))) throw new Error(`--frames takes whole frame offsets, got '${opt('frames')}'`);
      times = ks.map((k) => (F + k) / 30);
      names = ks.map((k) => `f${k >= 0 ? '+' : ''}${k}_${String(F + k).padStart(4, '0')}.png`);
    }
    const files = await stills(page, times, opt('out', path.join(ROOT, tr ? `out/transitions/${TRANSITION}` : 'out/stills'))!, names);
    console.log(files.join('\n'));
  } else if (mode === 'sheet') {
    // --only <scene>: its first and last frames are the first and last stills
    const clip = await sceneFrames(page, 30);
    const from = clip ? clip.first / 30 : +opt('from', '0')!, to = clip ? clip.last / 30 : +opt('to', '10')!, n = +opt('n', '12')!;
    let times = Array.from({ length: n }, (_, i) => from + ((to - from) * i) / Math.max(1, n - 1));
    if (tr && !flag('from') && !flag('to')) {
      // every frame of the window, and 3 either side (a 'cut': F − 3 … F + 2)
      const w = ownedFrames(tr, 30), F = ownedFrames({ start: tr.cut, end: tr.cut }, 30).first;
      const f0 = (w.last >= w.first ? w.first : F) - 3, f1 = (w.last >= w.first ? w.last : F - 1) + 3;
      times = Array.from({ length: f1 - f0 + 1 }, (_, i) => (f0 + i) / 30);
    }
    if (opt('times')) times = opt('times')!.split(',').map(Number);
    if (flag('cuts')) {
      // 4 frames around every timeline boundary: 2 frames before, 2 after
      const tl: { id: string; start: number }[] = await page.evaluate(() => (window as any).__film.timeline);
      times = tl.slice(1).flatMap((e) => [e.start - 0.1, e.start - 1 / 30, e.start + 1 / 30, e.start + 0.1]);
    }
    const out = opt('out', path.join(ROOT, tr ? `out/transitions/${TRANSITION}-sheet.png` : `out/sheets/sheet_${clip ? clip.id : `${from}-${to}`}.png`))!;
    await sheet(page, times, +opt('cols', '4')!, out);
    console.log(out);
  } else if (mode === 'perf') {
    // --only <scene>: from its first frame, and to half a frame past its last, where no sum of 1/30 steps lands
    const clip = await sceneFrames(page, 30);
    const from = clip ? clip.first / 30 : +opt('from', '0')!, to = clip ? (clip.last + 0.5) / 30 : +opt('to', '5')!;
    const r = await page.evaluate(async ({ from, to, samples, shutter }) => {
      const P = (window as any).__film;
      const ms: number[] = [];
      let prep = 0;
      const buf = new Uint8Array(P.width * P.height * 4);
      await P.still(from);
      const used: Record<number, number> = {};
      for (let t = from; t < to; t += 1 / 30) {
        const p0 = performance.now();
        await P.engine.prepare(t, 1 / 30, samples, shutter); // plate loads, outside the render timing
        const a = performance.now();
        prep += a - p0;
        const k = P.engine.render(t, 1 / 30, false, samples, shutter);
        used[k] = (used[k] ?? 0) + 1;
        await P.engine.readPixelsAsync(buf);
        ms.push(performance.now() - a);
      }
      ms.sort((a, b) => a - b);
      return { n: ms.length, avg: ms.reduce((a, b) => a + b, 0) / ms.length, p50: ms[ms.length >> 1], p95: ms[Math.floor(ms.length * 0.95)], max: ms[ms.length - 1], used, prep: prep / ms.length };
    }, { from, to, samples: SAMPLES, shutter: +opt('shutter', '0.5')! });
    console.log(`frames ${r.n}  avg ${r.avg.toFixed(1)}ms  p50 ${r.p50.toFixed(1)}  p95 ${r.p95.toFixed(1)}  max ${r.max.toFixed(1)}  sub-frames ${hist(r.used)}  (prepare ${r.prep.toFixed(1)}ms/frame, untimed)`);
  } else if (mode === 'video') {
    const dur: number = await page.evaluate(() => (window as any).__film.duration);
    const fps = +opt('fps', '30')!;
    // --only <scene>: from its first frame's time to the time after its last, both whole frames (stream() rounds
    // from·fps and to·fps, and the audio is cut at the same times)
    const clip = tr ? null : await sceneFrames(page, fps);
    // --transition: [start − 1, end + 1] (cut ± 1 for a 'cut'), on whole frames
    const trFrom = tr ? Math.floor((tr.start - 1) * fps) / fps : 0, trTo = tr ? Math.ceil((tr.end + 1) * fps) / fps : dur;
    const from = clip ? clip.first / fps : +opt('from', String(trFrom))!, to = clip ? (clip.last + 1) / fps : +opt('to', String(Math.min(dur, trTo)))!;
    // without --out, a part of the film is named after its scenes (or module), and a range given with --from/--to
    // after its times as well: only the whole film is out/gitloom.mp4, and only a scene's whole window out/<id>.mp4
    const name = (opt('module') ?? opt('only'))?.replace(/[,/]/g, '+') ?? 'gitloom';
    const range = !clip && (flag('from') || flag('to')) ? `_${from}-${to}` : '';
    const def = tr ? `out/transitions/${TRANSITION}${range}.mp4` : `out/${name}${range}.mp4`;
    await video(page, from, to, fps, path.resolve(opt('out', path.join(ROOT, def))!), gpu);
  }
} finally {
  // (a failed run too: what the page logged is often why)
  if (session?.logs.length) console.error('BROWSER LOG:\n' + session.logs.slice(0, 40).join('\n'));
  await session?.browser.close();
  stop();
}
