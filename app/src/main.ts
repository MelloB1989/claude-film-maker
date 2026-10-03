// Entry: preview player (default) or export mode (?export=1, driven by scripts/render.ts).
import { Engine, type AdaptiveSampling, type TimelineEntry } from './engine/engine';
import { PW, PH, SCALE } from './engine/gl';
import { unmaskedRenderer } from './engine/gpu';
import type { SceneClass } from './engine/scene';
import type { VO } from './engine/vo';
import type { AudioData } from './engine/audio';
import { makeTimeline, makeTransitions } from './timeline';
import { specOf, type TransitionModule } from './engine/transition';
import { FPS } from './engine/util';

const params = new URLSearchParams(location.search);
const EXPORT = params.has('export');
const ONLY = params.get('only'); // comma-separated scene ids to load (faster stills)
const FROM = params.get('t') ? parseFloat(params.get('t')!) : null;
// dev harness: ?module=<name> plays scenes/<name>.ts alone, over the whole film [0, duration] (render.ts --module)
const MODULE = params.get('module');
// review harness: ?transition=<file> plays transitions/<file>.ts as the film's only transition (a dev probe, _probe-*.ts,
// too), usually with only=<from>,<to> (render.ts --transition)
const TRANSITION = params.get('transition');

const canvas = document.getElementById('c') as HTMLCanvasElement;
// physical size: 1920x1080 times ?scale= (the page CSS keeps showing it at 1920x1080)
canvas.width = PW;
canvas.height = PH;

// (not the tests beside them, as in timeline.ts)
const sceneModules = import.meta.glob<{ default: SceneClass }>(['./scenes/*.ts', '!./scenes/*.test.ts']);

/** A timeline of one entry: scenes/<name>.ts from 0 to the end of the film (a harness like _stagetest, or any scene). */
function moduleTimeline(name: string) {
  return (vo: VO, audio: AudioData): TimelineEntry[] => [{
    id: name, file: name, start: 0, end: Math.max(audio.duration, vo.duration), params: { scene: name, module: true },
    load: () => {
      const m = sceneModules[`./scenes/${name}.ts`];
      return m ? m() : Promise.reject(new Error(`scene module not found: scenes/${name}.ts`));
    },
  }];
}

// every transition module, the dev probes included (not the tests beside them, as in timeline.ts)
const transitionModules = import.meta.glob<TransitionModule>(['./transitions/*.ts', '!./transitions/*.test.ts'], { eager: true });

/** The transitions ?transition=<file> plays: that module's alone. */
function oneTransition(file: string) {
  return (vo: VO) => {
    const m = transitionModules[`./transitions/${file}.ts`];
    if (!m) throw new Error(`transition module not found: transitions/${file}.ts`);
    return [specOf(m, vo)];
  };
}

const engine = new Engine(canvas, MODULE ? moduleTimeline(MODULE) : makeTimeline, MODULE ? undefined : TRANSITION ? oneTransition(TRANSITION) : makeTransitions);

declare global {
  interface Window { __film: any }
}

let TIMELINE: typeof engine.timeline = [];

async function boot() {
  const onlySet = ONLY && !MODULE ? new Set(ONLY.split(',')) : null;
  // export loads each scene when a frame first needs it, and a scene error fails the still or the export
  await engine.init(onlySet ? (e) => onlySet.has(e.id) : undefined, { exporting: EXPORT });
  TIMELINE = engine.timeline;
  if (EXPORT) setupExport();
  else setupPlayer();
}

// ------------------------------------------------------------------ export API
function setupExport() {
  document.body.classList.add('export');
  // A lost WebGL context (under heavy GPU load Chrome can reset the GPU process, or run the GPU out of memory): GL calls
  // after it do nothing, so what is rendered or read back is not the frame, and no scene reports it. A still or a stream
  // that finds the context lost rejects (the export fails), and no frame read after the loss is sent.
  const gl = engine.renderer.getContext();
  const LOST = 'the WebGL context was lost (the GPU process reset, or the GPU ran short of memory): frames rendered after it cannot be trusted';
  let lost = false;
  const whenLost = new Promise<never>((_, reject) => {
    canvas.addEventListener('webglcontextlost', () => {
      lost = true;
      reject(new Error(LOST));
    });
  });
  whenLost.catch(() => {}); // (nothing may be racing it: a loss between exports is found by the next still or stream)
  const assertLive = () => {
    if (lost || gl.isContextLost()) throw new Error(LOST);
  };
  /**
   * Run `work`, rejecting as soon as the context is lost, or if it is by the time `work` ends. Whatever a call died of
   * after the loss (a readback of a lost context rejects with undefined), the loss is the reason reported.
   */
  const guard = async <T>(work: () => Promise<T>): Promise<T> => {
    assertLive();
    try {
      const r = await Promise.race([work(), whenLost]);
      assertLive();
      return r;
    } catch (e) {
      assertLive();
      throw e;
    }
  };
  window.__film = {
    engine,
    duration: engine.duration,
    errors: engine.errors,
    /** The engine's unmasked renderer string (the GPU, or the software fallback); throws once the context is lost. */
    renderer: () => {
      assertLive();
      return unmaskedRenderer(gl);
    },
    /** Throws if the WebGL context was lost: what render.ts calls after it has captured a still. */
    assertLive,
    /** Output size in px (1920x1080 times scale); stream() sends frames of width*height*4 bytes. */
    scale: SCALE,
    width: PW,
    height: PH,
    timeline: TIMELINE.map(({ id, start, end }) => ({ id, start, end })),
    /** The transitions in play (validated): their windows around the cut. */
    transitions: engine.transitions.map(({ id, cut, start, end, spec }) => ({ id, cut, start, end, kind: spec.kind, from: spec.from, to: spec.to })),
    /**
     * Render a single frame at t (seeks as needed), once its scenes have loaded (the first still that needs one loads
     * it, and it stays) and prepared it (plates). Rejects on any scene error, and when the WebGL context is lost.
     */
    still(t: number, samples: number | AdaptiveSampling = 1, shutter = 0.5) {
      return guard(async () => {
        await engine.prepare(t, 1 / FPS, samples, shutter);
        return engine.render(t, 1 / FPS, true, samples, shutter);
      });
    },
    /** The last rendered frame as a full-resolution (PW x PH) PNG, base64 (for stills at scale > 1). Rejects when the context is lost. */
    async png() {
      const px = await guard(() => engine.readPixelsAsync()), row = PW * 4;
      const img = new ImageData(PW, PH);
      for (let y = 0; y < PH; y++) img.data.set(px.subarray((PH - 1 - y) * row, (PH - y) * row), y * row); // bottom-up -> top-down
      const oc = new OffscreenCanvas(PW, PH);
      oc.getContext('2d')!.putImageData(img, 0, 0);
      const b = new Uint8Array(await (await oc.convertToBlob({ type: 'image/png' })).arrayBuffer());
      let s = '';
      for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode(...b.subarray(i, i + 0x8000));
      return btoa(s);
    },
    /**
     * Render [from, to) at fps and stream raw RGBA frames (bottom-up) over a WebSocket (Engine.exportFrames: each
     * scene loads just before its first frame and goes after its last; a scene error rejects, and no frame after it
     * is sent). Returns when all frames were sent, with a histogram of sub-frames per frame. With `inflight`, the
     * receiver acknowledges each frame it has handed on (a text message with its running count) and at
     * most `inflight` frames are unacknowledged:
     * backpressure from the encoder, so a slow encode (4K) cannot pile frames up in the receiver's memory.
     * Rejects when the WebGL context is lost, however long ago: no frame read after the loss is sent.
     * `loseContextAfter` is for tests (render.ts --test-lose-context): the page loses its own context (WEBGL_lose_context)
     * once that frame is sent, which the stream must then fail on.
     */
    async stream(opts: { from: number; to: number; fps: number; ws: string; samples?: number | AdaptiveSampling; shutter?: number; inflight?: number; loseContextAfter?: number }) {
      const ws = new WebSocket(opts.ws);
      ws.binaryType = 'arraybuffer';
      let acked = 0, closed = false;
      ws.onmessage = (e) => { if (typeof e.data === 'string') acked = Math.max(acked, +e.data || 0); };
      await new Promise<void>((res, rej) => { ws.onopen = () => res(); ws.onerror = (e) => rej(e); });
      ws.onclose = () => { closed = true; }; // the receiver gave up (its encoder quit): stop, don't wait for acks
      try {
        const n0 = Math.round(opts.from * opts.fps);
        const buf = new Uint8Array(PW * PH * 4);
        const used = await guard(() => engine.exportFrames(opts, async (n) => {
          await engine.readPixelsAsync(buf);
          assertLive();
          if (opts.inflight) while (!closed && n - n0 - acked >= opts.inflight) await new Promise((r) => setTimeout(r, 2));
          if (closed) throw new Error(`the receiver closed the stream at frame ${n}`);
          while (ws.bufferedAmount > 64 * 1024 * 1024) await new Promise((r) => setTimeout(r, 2));
          ws.send(buf);
          if (n % 30 === 0) await new Promise((r) => setTimeout(r, 0)); // let the socket flush
          if (n === opts.loseContextAfter) gl.getExtension('WEBGL_lose_context')?.loseContext();
        }));
        while (ws.bufferedAmount > 0) await new Promise((r) => setTimeout(r, 5));
        return used;
      } finally {
        ws.close();
      }
    },
  };
  window.__film.ready = true;
}

// ------------------------------------------------------------------ preview player
function setupPlayer() {
  const audio = new Audio('audio/mix/mix.wav');
  audio.preload = 'auto';
  const ui = document.getElementById('ui')!;
  const scrub = document.getElementById('scrub') as HTMLInputElement;
  const info = document.getElementById('info')!;
  const marks = document.getElementById('marks')!;
  const errs = document.getElementById('errs')!;
  scrub.max = String(engine.duration);
  scrub.step = '0.001';
  if (engine.errors.length) { errs.textContent = engine.errors.join('\n\n'); errs.style.display = 'block'; }

  for (const e of TIMELINE) {
    const m = document.createElement('div');
    m.className = 'mark';
    m.style.left = `${(e.start / engine.duration) * 100}%`;
    m.style.width = `${((e.end - e.start) / engine.duration) * 100}%`;
    m.title = `${e.id} ${e.start.toFixed(2)}–${e.end.toFixed(2)}`;
    m.textContent = e.id;
    m.onclick = () => seek(e.start);
    marks.appendChild(m);
  }

  let t = FROM ?? 0;
  let playing = false;
  let loop: [number, number] | null = null;
  let lastAudioT = 0, lastPerf = 0;
  const seek = (x: number) => { t = Math.max(0, Math.min(engine.duration - 0.001, x)); audio.currentTime = t; };
  seek(t);

  const toggle = () => { playing = !playing; if (playing) { audio.currentTime = t; audio.play(); } else audio.pause(); };
  canvas.onclick = toggle;
  scrub.oninput = () => seek(parseFloat(scrub.value));
  window.addEventListener('keydown', (ev) => {
    if (ev.key === ' ') { ev.preventDefault(); toggle(); }
    if (ev.key === 'ArrowRight') seek(t + (ev.shiftKey ? 5 : 1));
    if (ev.key === 'ArrowLeft') seek(t - (ev.shiftKey ? 5 : 1));
    if (ev.key === '.') seek(t + 1 / FPS);
    if (ev.key === ',') seek(t - 1 / FPS);
    if (ev.key === 'l') {
      const e = TIMELINE.find((x) => t >= x.start && t < x.end);
      loop = loop ? null : e ? [e.start, e.end] : null;
    }
    if (ev.key === 'h') ui.classList.toggle('hidden');
    if (ev.key === ']') { const e = TIMELINE.find((x) => x.start > t + 0.01); if (e) seek(e.start); }
    if (ev.key === '[') { const es = TIMELINE.filter((x) => x.start < t - 0.3); const e = es[es.length - 1]; if (e) seek(e.start); }
  });

  // scenes load what a frame needs (plate frames) without holding the player up; a failure is logged once
  let prepErr = '';
  const prepare = (x: number) => engine.prepare(x).catch((e) => {
    const m = String(e?.message ?? e);
    if (m !== prepErr) { prepErr = m; console.warn(`prepare(${x.toFixed(3)}): ${m}`); }
  });

  let frames = 0, fpsT = performance.now(), fps = 0;
  const tick = () => {
    if (playing) {
      // smooth the coarse audio clock with performance.now()
      const now = performance.now();
      if (audio.currentTime !== lastAudioT) { lastAudioT = audio.currentTime; lastPerf = now; }
      t = lastAudioT + (audio.paused ? 0 : (now - lastPerf) / 1000);
      if (loop && t >= loop[1]) seek(loop[0]);
      if (audio.ended) playing = false;
    }
    prepare(t);
    engine.render(t, 1 / FPS);
    scrub.value = String(t);
    frames++;
    const now = performance.now();
    if (now - fpsT > 500) { fps = (frames * 1000) / (now - fpsT); frames = 0; fpsT = now; }
    const e = TIMELINE.find((x) => t >= x.start && t < x.end);
    const l = engine.vo.lineAt(t);
    info.textContent = `${t.toFixed(2)}s  beat ${engine.audio.beatAt(t).toFixed(2)}  bar ${engine.audio.barAt(t).toFixed(2)}  [${e?.id ?? '—'}]  ${fps.toFixed(0)}fps   ${l ? '“' + l.text + '”' : ''}${loop ? '  LOOP' : ''}`;
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);

  // Vite HMR: re-instantiate scenes whose module changed
  if (import.meta.hot) {
    import.meta.hot.on('vite:afterUpdate', (payload: any) => {
      for (const u of payload.updates ?? []) {
        const m = /scenes\/([\w-]+)\.ts/.exec(u.path ?? '');
        if (m) for (const e of TIMELINE) if (e.id === m[1] || (e as any).file === m[1]) engine.reload(e.id);
      }
    });
  }
}

boot().catch((e) => {
  console.error(e);
  document.body.insertAdjacentHTML('beforeend', `<pre style="color:#f55;position:fixed;top:0;left:0">${String(e?.stack ?? e)}</pre>`);
  window.__film = { error: String(e?.stack ?? e) };
});
