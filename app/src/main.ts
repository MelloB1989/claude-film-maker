// Entry: preview player (default) or export mode (?export=1, driven by scripts/render.ts), for one film:
// films/<id>/film.ts, picked by ?film=<id> (else the build's FILM, else 'showcase').
import { Engine, type AdaptiveSampling, type TimelineEntry } from './engine/engine';
import { PW, PH, SCALE, W, H } from './engine/gl';
import { unmaskedRenderer } from './engine/gpu';
import type { SceneClass } from './engine/scene';
import type { VO } from './engine/vo';
import type { AudioData } from './engine/audio';
import type { FilmSpec } from './engine/film';
import { filmUrl } from './engine/config';
import { FPS } from './engine/util';

const params = new URLSearchParams(location.search);
const EXPORT = params.has('export');
const ONLY = params.get('only'); // comma-separated shot ids to load (faster stills)
const FROM = params.get('t') ? parseFloat(params.get('t')!) : null;
// dev harness: ?module=<name> plays films/<id>/scenes/<name>.ts alone, over the whole film (render.ts --module)
const MODULE = params.get('module');
// review harness: ?transition=<from>-<to> plays that one of the film's transitions alone, usually with only=<from>,<to>
// (render.ts --transition)
const TRANSITION = params.get('transition');

const FILMS = import.meta.glob<{ default: FilmSpec }>('../../films/*/film.ts');
const SCENES = import.meta.glob<{ default: SceneClass }>(['../../films/*/scenes/*.ts', '!../../films/*/scenes/*.test.ts']);
const FILM_ID = params.get('film') || (import.meta.env.VITE_FILM as string | undefined) || 'showcase';

const canvas = document.getElementById('c') as HTMLCanvasElement;

async function loadFilm(): Promise<FilmSpec> {
  const m = FILMS[`../../films/${FILM_ID}/film.ts`];
  if (!m) throw new Error(`no film '${FILM_ID}' (films: ${Object.keys(FILMS).map((k) => k.split('/')[3]).join(', ') || 'none'}): pass ?film=<id>`);
  const film = (await m()).default;
  if (film.id !== FILM_ID) throw new Error(`films/${FILM_ID}/film.ts says its id is '${film.id}': the id is the folder's name`);
  return film;
}

/** A timeline of one entry: films/<id>/scenes/<name>.ts over the whole film (a dev harness, or any scene). */
function moduleTimeline(name: string, duration: number) {
  return (_vo: VO, _audio: AudioData): TimelineEntry[] => [{
    id: name, file: name, start: 0, end: duration, params: { shot: name, module: true },
    load: () => {
      const m = SCENES[`../../films/${FILM_ID}/scenes/${name}.ts`];
      return m ? m() : Promise.reject(new Error(`scene module not found: films/${FILM_ID}/scenes/${name}.ts`));
    },
  }];
}

let engine: Engine;
declare global {
  interface Window { __film: any }
}

let TIMELINE: TimelineEntry[] = [];

async function boot() {
  const film = await loadFilm();
  engine = new Engine(canvas, film, {
    timeline: MODULE ? moduleTimeline(MODULE, film.duration ?? 10) : undefined,
    transitions: TRANSITION ? (all) => {
      const one = all.filter((x) => `${x.from}-${x.to}` === TRANSITION);
      if (!one.length) throw new Error(`the film has no transition ${TRANSITION} (it has: ${all.map((x) => `${x.from}-${x.to}`).join(', ') || 'none'})`);
      return one;
    } : undefined,
  });
  // physical size: the film's format times ?scale= (the page shows it at its logical size)
  canvas.width = PW;
  canvas.height = PH;
  canvas.style.aspectRatio = `${W} / ${H}`;
  document.title = film.title ?? film.id;
  const onlySet = ONLY && !MODULE ? new Set(ONLY.split(',')) : null;
  // export loads each scene when a frame first needs it, and a scene error fails the still or the export
  await engine.init(onlySet ? (e) => onlySet.has(e.id) : undefined, { exporting: EXPORT });
  TIMELINE = engine.timeline;
  if (EXPORT) setupExport(film);
  else setupPlayer(film);
}

// ------------------------------------------------------------------ export API
function setupExport(film: FilmSpec) {
  document.body.classList.add('export');
  canvas.style.width = `${W}px`;
  canvas.style.height = `${H}px`;
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
    /** The film: its id, title, logical format, frame rate and the audio the export muxes (relative to the film). */
    film: { id: film.id, title: film.title ?? film.id, format: [W, H], fps: FPS, mix: film.audio?.mix ?? null },
    /** Output size in px (the format times scale); stream() sends frames of width*height*4 bytes. */
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
/**
 * The player's clock: the film's mix when it has one (smoothed with performance.now(), as the media clock is coarse),
 * otherwise a silent clock that runs on performance.now().
 */
interface Clock { readonly paused: boolean; readonly ended: boolean; currentTime: number; play(): void; pause(): void }

function silentClock(duration: number): Clock {
  let at = 0, since = 0, paused = true;
  const now = () => (paused ? at : at + (performance.now() - since) / 1000);
  return {
    get paused() { return paused; },
    get ended() { return now() >= duration; },
    get currentTime() { return Math.min(now(), duration); },
    set currentTime(x: number) { at = x; since = performance.now(); },
    play() { if (paused) { since = performance.now(); paused = false; } },
    pause() { if (!paused) { at = now(); paused = true; } },
  };
}

function setupPlayer(film: FilmSpec) {
  let audio: Clock;
  if (film.audio?.mix) {
    const el = new Audio(filmUrl(film.audio.mix));
    el.preload = 'auto';
    audio = el;
  } else audio = silentClock(engine.duration);
  const ui = document.getElementById('ui')!;
  const scrub = document.getElementById('scrub') as HTMLInputElement;
  const info = document.getElementById('info')!;
  const marks = document.getElementById('marks')!;
  const errs = document.getElementById('errs')!;
  scrub.max = String(engine.duration);
  scrub.step = '0.001';
  if (engine.errors.length) { errs.textContent = engine.errors.join('\n\n'); errs.style.display = 'block'; }

  // the film picker (every films/*/film.ts), the format, and the safe areas: action 5%, title 10% in from each edge
  const pick = document.getElementById('films') as HTMLSelectElement;
  for (const id of Object.keys(FILMS).map((k) => k.split('/')[3]!).sort()) pick.add(new Option(id, id, id === film.id, id === film.id));
  pick.onchange = () => { const q = new URLSearchParams(location.search); q.set('film', pick.value); q.delete('t'); location.search = q.toString(); };
  document.getElementById('fmt')!.textContent = `${W}×${H} @ ${FPS} fps · ${engine.duration.toFixed(2)} s · ${TIMELINE.filter((e) => e.kind !== 'overlay').length} shots · ${engine.transitions.length} transitions`;
  for (const [id, k] of [['action', 0.05], ['title', 0.1]] as const) Object.assign(document.getElementById(id)!.style, { inset: `${k * 100}% ${k * 100}%` });
  /** The frame on screen as a PNG download (named for the film and the time). */
  const snapshot = () => canvas.toBlob((b) => {
    if (!b) return;
    const a = document.createElement('a');
    a.href = URL.createObjectURL(b);
    a.download = `${film.id}_${t.toFixed(3)}s.png`;
    a.click();
    URL.revokeObjectURL(a.href);
  }, 'image/png');

  for (const e of TIMELINE) {
    if (e.kind === 'overlay') continue;
    const m = document.createElement('div');
    m.className = 'mark';
    m.style.left = `${(e.start / engine.duration) * 100}%`;
    m.style.width = `${((e.end - e.start) / engine.duration) * 100}%`;
    m.title = `${e.id} ${e.start.toFixed(2)}–${e.end.toFixed(2)}`;
    m.textContent = e.id;
    m.onclick = () => seek(e.start);
    marks.appendChild(m);
  }

  // a reload (an edit to a scene or film.ts reloads the page) comes back to where it was, per film
  const KEY = `film-player:${film.id}`;
  let saved: { t?: number } = {};
  try {
    saved = JSON.parse(sessionStorage.getItem(KEY) ?? '{}');
  } catch {
    // no session storage: start from 0
  }
  let t = FROM ?? saved.t ?? 0;
  window.addEventListener('pagehide', () => {
    try {
      sessionStorage.setItem(KEY, JSON.stringify({ t }));
    } catch {
      // nothing to keep it in
    }
  });
  let playing = false;
  let loop: [number, number] | null = null;
  let lastAudioT = 0, lastPerf = 0;
  const seek = (x: number) => { t = Math.max(0, Math.min(engine.duration - 0.001, x)); audio.currentTime = t; };
  seek(t);

  const toggle = () => { playing = !playing; if (playing) { audio.currentTime = t; void audio.play(); } else audio.pause(); };
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
    if (ev.key === 'g') document.getElementById('safe')!.classList.toggle('on');
    if (ev.key === 'p') snapshot();
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
    info.textContent = `${film.title ?? film.id}  ${t.toFixed(2)}s  beat ${engine.audio.beatAt(t).toFixed(2)}  bar ${engine.audio.barAt(t).toFixed(2)}  [${e?.id ?? '—'}]  ${fps.toFixed(0)}fps   ${l ? '“' + l.text + '”' : ''}${loop ? '  LOOP' : ''}`;
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
