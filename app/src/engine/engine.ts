// The engine: owns the renderer, loads scenes for the timeline, renders any song time
// deterministically (with preroll for stateful scenes), composites transitions and overlays, HUD, post.
import * as THREE from 'three';
import { AudioData } from './audio';
import { VO } from './vo';
import { Compositor, FSPass, W, H, PW, PH, SCALE, SS_TAP, makeRT, clearRT } from './gl';
import { DEFAULT_POST, Post, SHOULDER_GLSL, type PostParams } from './post';
import { Hud } from './hud';
import type { Frame, Scene, SceneClass, SceneCtx, PostOverrides } from './scene';
import { HOLD, shutterTaps, sideTime, tapCount, transitionEntries, type Handles, type TransitionEntry, type TransitionSpec, type TransitionState } from './transition';
import { TransitionPass } from './transition-gl';
import { loadFonts } from './type';
import { loadStrokeFonts } from './stroke';
import { FPS } from './util';

export interface TimelineEntry {
  id: string;
  /** Lazy module loader; the module's default export is the Scene class. */
  load: () => Promise<{ default: SceneClass }>;
  /** Scene module file name, when it differs from the id (the animatic card); used by Vite HMR in preview. */
  file?: string;
  start: number;
  end: number;
  /** Default post overrides for this entry (the scene's own overrides win). */
  post?: PostOverrides;
  /** Free-form params handed to the scene as ctx.params. */
  params?: Record<string, any>;
  /** Cap on adaptive motion-blur sub-frames while this entry is on screen (for noise that converges slowly). */
  maxSamples?: number;
  /**
   * 'scene' (default): one of the film's shots, cut to or transitioned into its neighbours. 'overlay': drawn over the
   * scenes (alpha-premultiplied, 'normal' blend), after them in start order, at its own times, never crossfaded.
   */
  kind?: 'scene' | 'overlay';
}

interface Loaded {
  entry: TimelineEntry;
  scene: Scene | null;
  error?: string;
  lastT: number;
  /** Export: the scene's load in flight (module, construct, init), which concurrent prepares share. */
  loading?: Promise<Scene>;
  /** Export: the scene has rendered since it loaded (prepare's warm-up). */
  warm?: boolean;
}

/**
 * Per-frame adaptive motion-blur sampling (see Engine.render): the sub-frame count steps through
 * 4, 12, 36, 108, 324 … from `min` up to at most `max` (both rounded to that series) until the frame's
 * estimated remaining sampling error is below `tol` 8-bit levels everywhere (worst 2x2-logical-px block).
 */
export interface AdaptiveSampling { min: number; max: number; tol: number }

/**
 * Shutter offsets (-0.5..0.5) of an adaptive run's sub-frames in rendering order: 4 evenly spread, then
 * each step splits every interval in three, adding a sub-frame either side of each old one. Every
 * prefix of 4·3^l is then evenly spread and centred on the frame's time, and so is each step's new set:
 * comparing the new set's average with the old one's measures sampling error, not a shift in time
 * (with doublings the new half sits half a step later, and any motion at all would read as error).
 */
function ternaryOffsets(steps: number) {
  const u = [0, 1, 2, 3].map((i) => (i + 0.5) / 4 - 0.5);
  for (let l = 0, n = 4; l < steps; l++, n *= 3)
    for (let m = 0; m < n; m++) u.push((3 * m + 0.5) / (3 * n) - 0.5, (3 * m + 2.5) / (3 * n) - 0.5);
  return u;
}

/** An adaptive run's steps (Engine.render): it starts at 4·3^lo sub-frames and may go on to 4·3^hi, hi from `max`. */
function adaptiveSteps(s: AdaptiveSampling, max = s.max) {
  const lg3 = (x: number) => Math.log(x / 4) / Math.log(3);
  const lo = Math.max(0, Math.round(lg3(s.min)));
  return { lo, hi: Math.max(lo, Math.floor(lg3(max) + 1e-9)) };
}

/**
 * The shutter offsets (-0.5..0.5) of a frame's sub-frames, in rendering order: a fixed count evenly spread ([0] for
 * one), and for adaptive sampling every sub-frame a run may render (ternaryOffsets up to `max`: a run that converges
 * early, or is capped by an entry's maxSamples, renders a prefix). render() takes its sub-frames from this one list and
 * prepare() prepares them, so what a frame renders has always been loaded.
 */
export function shutterOffsets(samples: number | AdaptiveSampling): number[] {
  if (typeof samples !== 'number') return ternaryOffsets(adaptiveSteps(samples).hi);
  return Array.from({ length: samples }, (_, k) => (k + 0.5) / samples - 0.5);
}

/** A timeline window: song seconds [start, end). */
export type Span = Pick<TimelineEntry, 'start' | 'end'>;

/**
 * An entry to render in one sub-frame, and the time to render it at; `held` when that time is held inside the entry's
 * window (the sub-frame falls before its start or at or past its end): no time passes for it there.
 */
export interface EntryAt<E extends Span = TimelineEntry> { entry: E; time: number; held: boolean }

/** The entries on screen in the frame at t: those whose window [start, end) holds t, in compositing order (by start). */
export function onScreen<E extends Span>(timeline: readonly E[], t: number): E[] {
  return timeline.filter((e) => t >= e.start && t < e.end).sort((a, b) => a.start - b.start);
}

/**
 * The cut-aware shutter: what each sub-frame of the frame at t renders, and at what time. A camera exposes a frame
 * within one shot, so every sub-frame shows the entries on screen at the frame's own time t (onScreen), each at the
 * sub-frame's time t + dt·shutter·u (u = `offsets[k]`, -0.5..0.5) held inside its own window: before it, at its start;
 * at or past its end, HOLD before it. An entry that ends inside the shutter holds its last instant, one that starts
 * inside it after t first shows on the next frame, and one whose window covers the shutter (an overlay across a cut)
 * is untouched. (Sub-frames from both sides of a hard cut would ghost the next shot into the frame before it.)
 * Returns, per sub-frame, its entries in compositing order.
 */
export function shutterPlan<E extends Span>(timeline: readonly E[], t: number, dt: number, shutter: number, offsets: readonly number[]): EntryAt<E>[][] {
  const on = onScreen(timeline, t);
  return offsets.map((u) => {
    const s = t + dt * shutter * u;
    return on.map((entry) => (s < entry.start ? { entry, time: entry.start, held: true } : s < entry.end ? { entry, time: s, held: false } : { entry, time: entry.end - HOLD, held: true }));
  });
}

/**
 * The frames a timeline window owns at `fps`: frame f is the window's when the window is on screen at the frame's time
 * f / fps, so [start, end) owns frames ceil(start·fps) … ceil(end·fps) − 1 (`last` < `first` when it holds none).
 * Counted on the frame times themselves: a boundary exactly on a frame time gives that frame to the later window even
 * where start·fps rounds past the integer (8.3·30 is 249.00000000000003, and frame 249 is at 8.3).
 */
export function ownedFrames(w: Span, fps: number): { first: number; last: number } {
  // the first frame at or after x
  const from = (x: number) => {
    let f = Math.ceil(x * fps);
    while ((f - 1) / fps >= x) f--;
    while (f / fps < x) f++;
    return f;
  };
  return { first: from(w.start), last: from(w.end) - 1 };
}

/**
 * The two frames a still at t straddles, when t·fps is within `tol` frames of half way between them (n + 0.5): its
 * shutter takes sub-frames from both frames' states (a Panel's text, anything on the frame grid), a blend no export ever
 * renders (its frames are at n / fps). Null for a time inside one frame's state. render.ts stills warns of them.
 */
export function straddledFrames(t: number, fps: number, tol = 0.1): [number, number] | null {
  const x = t * fps, n = Math.floor(x);
  return Math.abs(x - n - 0.5) < tol ? [n, n + 1] : null;
}

/**
 * One layer of a sub-frame, in compositing order: a scene at its time; a transition, its two scenes each at its side
 * time (sideTime), drawn by TransitionPass; or an overlay at its own time, drawn over what is below it.
 */
export type Layer<E extends Span = TimelineEntry> =
  | { kind: 'scene'; at: EntryAt<E> }
  | { kind: 'transition'; tr: TransitionEntry; a: EntryAt<E>; b: EntryAt<E> }
  | { kind: 'overlay'; at: EntryAt<E> };

const NO_HANDLES: Handles = { head: 0, tail: 0 };

/**
 * What each sub-frame of the frame at t renders: per shutter offset (`offsets`, as shutterPlan takes them), its layers in
 * compositing order. Scene entries come first, then overlays (kind 'overlay') in start order, each at its own time held
 * in its window (shutterPlan). When t lies in a transition's window [start, end), its two scenes are one transition
 * layer instead, each side at sideTime(its mode, the sub-frame's time, its window, its handles): 'hold' clamps into the
 * scene's own window, 'run' into its handles. Otherwise the scenes are exactly shutterPlan's, as scene layers. (The
 * transition's own motion is not per sub-frame: render() draws every sub-frame with the frame's shutterTaps.)
 */
export function framePlan<E extends Span & { id: string; kind?: 'scene' | 'overlay' }>(timeline: readonly E[], transitions: readonly TransitionEntry[], t: number, dt: number, shutter: number, offsets: readonly number[], handles: (id: string) => Handles = () => NO_HANDLES): Layer<E>[][] {
  const scenes = timeline.filter((e) => e.kind !== 'overlay'), overlays = timeline.filter((e) => e.kind === 'overlay');
  const ov = shutterPlan(overlays, t, dt, shutter, offsets);
  const tr = transitions.find((x) => t >= x.start && t < x.end);
  const a = tr && scenes.find((e) => e.id === tr.spec.from), b = tr && scenes.find((e) => e.id === tr.spec.to);
  if (!tr || !a || !b) {
    const sc = shutterPlan(scenes, t, dt, shutter, offsets);
    return sc.map((sub, k) => [...sub.map((at) => ({ kind: 'scene' as const, at })), ...ov[k]!.map((at) => ({ kind: 'overlay' as const, at }))]);
  }
  const ha = handles(a.id), hb = handles(b.id);
  return offsets.map((u, k) => {
    const s = t + dt * shutter * u;
    const layer: Layer<E> = {
      kind: 'transition', tr,
      a: { entry: a, ...sideTime(tr.spec.fromMode ?? 'hold', s, a, ha) },
      b: { entry: b, ...sideTime(tr.spec.toMode ?? 'hold', s, b, hb) },
    };
    return [layer, ...ov[k]!.map((at) => ({ kind: 'overlay' as const, at }))];
  });
}

/** The entries a sub-frame's layers render (a transition: both its sides), in compositing order. */
export function layerEntries<E extends Span>(sub: readonly Layer<E>[]): EntryAt<E>[] {
  return sub.flatMap((l) => (l.kind === 'transition' ? [l.a, l.b] : [l.at]));
}

/**
 * A frame shows one scene, or two inside a transition's window: scene windows (entries not 'overlay') never overlap.
 * Throws naming the two that do (Engine.init).
 */
export function checkScenes(timeline: readonly (Span & { id: string; kind?: 'scene' | 'overlay' })[]) {
  const sc = timeline.filter((e) => e.kind !== 'overlay').sort((a, b) => a.start - b.start);
  for (let i = 1; i < sc.length; i++) {
    const p = sc[i - 1]!, q = sc[i]!;
    if (q.start < p.end) throw new Error(`scenes ${p.id} [${p.start}, ${p.end}) and ${q.id} [${q.start}, ${q.end}) overlap: two scenes share a frame only inside a transition's window (transitions/<from>-<to>.ts), and an overlay is kind 'overlay'`);
  }
}

/** When an entry is last needed: the end of its window, or of a transition out of it if later. */
export function lastUse(e: Span & { id: string }, transitions: readonly TransitionEntry[]): number {
  return transitions.reduce((m, x) => (x.spec.from === e.id ? Math.max(m, x.end) : m), e.end);
}

/** When an entry is first needed: the start of its window, or of a transition into it if earlier. */
export function firstUse(e: Span & { id: string }, transitions: readonly TransitionEntry[]): number {
  return transitions.reduce((m, x) => (x.spec.to === e.id ? Math.min(m, x.start) : m), e.start);
}

export class Engine {
  renderer: THREE.WebGLRenderer;
  ctx!: SceneCtx;
  audio!: AudioData;
  vo!: VO;
  hud!: Hud;
  post!: Post;
  comp = new Compositor();
  loaded = new Map<string, Loaded>();
  /**
   * Each layer of a sub-frame renders into a target of its own, and no pass reads the target it writes: a scene layer
   * into sceneRT; a transition's sides into trA and trB and its pass into trOut; an overlay into ovRT, drawn over what is
   * below it into one of the overlays' ping-pong pair (made when an overlay first renders).
   */
  private sceneRT = makeRT();
  private trA = makeRT();
  private trB = makeRT();
  private trOut = makeRT(W, H, { depthBuffer: false });
  private ovRT: THREE.WebGLRenderTarget | null = null;
  private ovPP: THREE.WebGLRenderTarget[] = [];
  private trPass: TransitionPass | null = null;
  // motion-blur sub-frame sums (float: up to hundreds of sub-frames), their average, and the error estimate
  private sumRT = makeRT(W, H, { depthBuffer: false, type: THREE.FloatType });
  private newRT = makeRT(W, H, { depthBuffer: false, type: THREE.FloatType });
  private avgRT = makeRT(W, H, { depthBuffer: false });
  private errRT: THREE.WebGLRenderTarget;
  private maxRT: THREE.WebGLRenderTarget;
  private errPass: FSPass;
  private maxPass: FSPass;
  private errBuf: Float32Array;
  /** Sub-frames used for the last rendered frame, and its estimated sampling error after each step. */
  lastSamples = 1;
  lastErrors: number[] = [];
  private finalRT = new THREE.WebGLRenderTarget(PW, PH, { type: THREE.UnsignedByteType, depthBuffer: false });
  private blit: FSPass;
  private accum: FSPass;
  private lastT = -1;
  lastPost: PostParams = { ...DEFAULT_POST };
  /** Every scene failure (init, prepare, render). In export each is also thrown: the still, or the export, fails. */
  errors: string[] = [];
  /** Suppress the HUD (crop marks). */
  hudOff = false;
  /**
   * Export (init({ exporting: true })): a scene loads when a frame first needs it (prepare) and an export lets it go
   * after its last frame (releaseEnded), and a scene error is fatal instead of a red frame.
   */
  exporting = false;

  timeline: TimelineEntry[] = [];
  /** The film's transitions (makeTransitions, validated against vo.json at init), in cut order. */
  transitions: TransitionEntry[] = [];

  constructor(public canvas: HTMLCanvasElement, private makeTimeline: (vo: VO, audio: AudioData) => TimelineEntry[], private makeTransitions?: (vo: VO) => TransitionSpec[]) {
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: false, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(1);
    this.renderer.setSize(PW, PH, false);
    this.renderer.autoClear = false;
    // glass (transmission) refracts a copy of the frame three renders per scene and camera, at 4x MSAA with mips: at
    // the layout's 1920x1080 whatever the output scale (satin glass needs no 4K refraction; about 464 MiB at 4K)
    this.renderer.transmissionResolutionScale = 1 / SCALE;
    this.blit = new FSPass(`uniform sampler2D src; void main(){ fragColor = texture(src, vUv); }`, { src: { value: null } });
    // adds a sub-frame to a sum; a non-finite pixel (a stray NaN from some shader in one sub-frame out of
    // hundreds) is dropped, or it would poison the average and bloom into a disc
    this.accum = new FSPass(`uniform sampler2D src;
      void main() {
        vec4 c = texture(src, vUv);
        bool ok = abs(c.r) <= 6e4 && abs(c.g) <= 6e4 && abs(c.b) <= 6e4 && abs(c.a) <= 6e4;
        fragColor = ok ? c : vec4(0.0);
      }`, { src: { value: null } }, { blending: THREE.CustomBlending, transparent: true });
    const am = this.accum.mat;
    am.blendEquation = THREE.AddEquation;
    am.blendSrc = THREE.OneFactor; am.blendDst = THREE.OneFactor;
    am.blendSrcAlpha = THREE.ZeroFactor; am.blendDstAlpha = THREE.OneFactor;
    // sampling error: per block of B x B physical px (2x2 logical), how far the displayed average moves when a
    // step's new sub-frames (2n, summed in b) are merged with the n before them (summed in a): 2/3 of the gap
    const B = 2 * SCALE, ew = Math.ceil(PW / B), eh = Math.ceil(PH / B), R = 16;
    const small = { depthBuffer: false, type: THREE.FloatType, minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter, pxScale: 1 } as const;
    this.errRT = makeRT(ew, eh, small);
    this.maxRT = makeRT(Math.ceil(ew / R), Math.ceil(eh / R), small);
    this.errBuf = new Float32Array(this.maxRT.width * this.maxRT.height * 4);
    this.errPass = new FSPass(/* glsl */ `
      uniform sampler2D a; uniform sampler2D b; uniform float invA, invB;
      ${SHOULDER_GLSL}
      vec3 disp(vec3 x) { return toSRGB(sat(shoulder(max(x, 0.0)))); }
      void main() {
        ivec2 p0 = ivec2(gl_FragCoord.xy) * ${B}, lim = ivec2(${PW - 1}, ${PH - 1});
        vec3 sa = vec3(0.0), sb = vec3(0.0);
        for (int y = 0; y < ${B}; y++) for (int x = 0; x < ${B}; x++) {
          ivec2 p = min(p0 + ivec2(x, y), lim);
          sa += texelFetch(a, p, 0).rgb; sb += texelFetch(b, p, 0).rgb;
        }
        vec3 e = abs(disp(sa * (invA / ${B * B}.0)) - disp(sb * (invB / ${B * B}.0)));
        fragColor = vec4(170.0 * max(e.r, max(e.g, e.b)), 0.0, 0.0, 1.0);
      }`, { a: { value: null }, b: { value: null }, invA: { value: 1 }, invB: { value: 1 } });
    this.maxPass = new FSPass(/* glsl */ `
      uniform sampler2D e;
      void main() {
        ivec2 p0 = ivec2(gl_FragCoord.xy) * ${R};
        float m = 0.0;
        for (int y = 0; y < ${R}; y++) for (int x = 0; x < ${R}; x++) {
          ivec2 p = p0 + ivec2(x, y);
          if (p.x < ${ew} && p.y < ${eh}) m = max(m, texelFetch(e, p, 0).r);
        }
        fragColor = vec4(m, 0.0, 0.0, 1.0);
      }`, { e: { value: null } });
  }

  /**
   * Load the film's data and the timeline's scenes: those `only` passes (--only; the rest render as red fill). The
   * player loads every scene now, to scrub anywhere without a stall; export (`exporting`) loads none yet: each loads
   * when a frame first needs it (prepare), so an export holds only the scenes on screen.
   */
  async init(only?: (e: TimelineEntry) => boolean, opts: { exporting?: boolean } = {}) {
    this.exporting = !!opts.exporting;
    [this.audio, this.vo] = await Promise.all([AudioData.load(), VO.load(), loadFonts(), loadStrokeFonts()]) as [AudioData, VO, void, void];
    this.timeline = this.makeTimeline(this.vo, this.audio);
    this.transitions = transitionEntries(this.makeTransitions?.(this.vo) ?? [], this.vo.scenes, this.vo.words);
    checkScenes(this.timeline);
    this.ctx = { renderer: this.renderer, audio: this.audio, vo: this.vo, comp: this.comp, W, H, id: '', params: {}, start: 0, end: 0 };
    this.post = new Post();
    this.hud = new Hud();
    const entries = only ? this.timeline.filter(only) : this.timeline;
    if (this.exporting) for (const e of entries) this.loaded.set(e.id, { entry: e, scene: null, lastT: -1 });
    else await Promise.all(entries.map((e) => this.loadEntry(e)));
  }

  /** Import an entry's module, construct its scene and init it (a failed init disposes what it built, best effort). */
  private async construct(e: TimelineEntry): Promise<Scene> {
    const mod = await e.load();
    const s = new mod.default({ ...this.ctx, id: e.id, params: e.params ?? {}, start: e.start, end: e.end });
    try {
      await s.init();
    } catch (err) {
      try {
        s.dispose();
      } catch {
        // half built: its dispose may trip on what init never made
      }
      throw err;
    }
    return s;
  }

  /** Player: load an entry's scene now; a failure is logged, and the scene renders as red fill. */
  private async loadEntry(e: TimelineEntry) {
    const rec: Loaded = { entry: e, scene: null, lastT: -1 };
    this.loaded.set(e.id, rec);
    try {
      rec.scene = await this.construct(e);
    } catch (err) {
      rec.error = String((err as Error)?.stack ?? err);
      this.errors.push(`[${e.id}] ${rec.error}`);
      console.error(`scene ${e.id} failed`, err);
    }
  }

  /** Export: an entry's scene, loaded the first time a frame needs it (one load, however many prepares ask at once). */
  private load(rec: Loaded): Promise<Scene> {
    if (rec.scene) return Promise.resolve(rec.scene);
    return (rec.loading ??= this.construct(rec.entry).then(
      (s) => {
        rec.scene = s;
        rec.lastT = -1;
        rec.loading = undefined;
        rec.warm = false;
        return s;
      },
      (err) => {
        rec.loading = undefined;
        throw this.fail(rec.entry, 'init', err);
      },
    ));
  }

  /** Export: dispose an entry's scene (its plates, layers, targets and GPU memory); a later frame would load it anew. */
  private unload(rec: Loaded) {
    const s = rec.scene;
    rec.scene = null;
    rec.lastT = -1;
    rec.warm = false;
    try {
      s?.dispose();
    } catch (err) {
      throw this.fail(rec.entry, 'dispose', err);
    }
  }

  /**
   * Export: dispose every loaded scene last needed at or before t (lastUse: its window's end, or the end of a transition
   * out of it). An export renders its frames in order, so from the frame at t on such a scene is never rendered again:
   * what it holds goes now, not at the end.
   */
  releaseEnded(t: number) {
    if (!this.exporting) return;
    for (const rec of this.loaded.values()) if (rec.scene && lastUse(rec.entry, this.transitions ?? []) <= t) this.unload(rec);
  }

  /** A scene's handles (Scene.handles), once it is loaded; none before. */
  private handlesOf(id: string): Handles {
    return this.loaded.get(id)?.scene?.handles ?? { head: 0, tail: 0 };
  }

  /** The frame at t's layers per sub-frame (framePlan over this engine's timeline and transitions). */
  plan(t: number, dt: number, shutter: number, offsets: readonly number[]): Layer[][] {
    return framePlan(this.timeline, this.transitions ?? [], t, dt, shutter, offsets, (id) => this.handlesOf(id));
  }

  /** The entries the frame at t renders (a transition's two sides included), in compositing order. */
  private entriesAt(t: number): TimelineEntry[] {
    return layerEntries(this.plan(t, 0, 0, [0])[0] ?? []).map((x) => x.entry);
  }

  /**
   * Records a scene's failure in `errors` and returns it as an error to throw (export), naming the scene and the step:
   * `scene <id> <what> failed: <message>`.
   */
  private fail(e: TimelineEntry, what: string, err: unknown): Error {
    this.errors.push(`[${e.id}] ${what}: ${String((err as Error)?.stack ?? err)}`);
    console.error(`scene ${e.id} ${what} failed`, err);
    return new Error(`scene ${e.id} ${what} failed: ${(err as Error)?.message ?? err}`, { cause: err });
  }

  /** Hot-swap a scene module (used by Vite HMR in preview). */
  async reload(id: string) {
    const e = this.timeline.find((x) => x.id === id);
    if (!e) return;
    this.loaded.get(id)?.scene?.dispose();
    await this.loadEntry(e);
    this.lastT = -1;
  }

  get duration() { return Math.max(this.audio.duration, this.vo.duration); }

  /**
   * Await prepare() of every scene the frame at t renders (as render() decides it, see framePlan: a transition's two
   * sides too), at each time a sub-frame of it will render the scene: from the one list of shutter offsets render()
   * takes (shutterOffsets), held in the scene's window (or a transition side's, sideTime) as its sub-frames are (a plate
   * dedups the times that share a plate frame). Export calls it before rendering each frame, render() staying
   * synchronous, and loads a scene here the first time a frame needs it (before the plan, which reads its handles); a
   * scene that fails to load or prepare rejects it.
   */
  async prepare(t: number, dt = 1 / FPS, samples: number | AdaptiveSampling = 1, shutter = 0.5): Promise<void> {
    const on = this.entriesAt(t);
    const recs = on.map((e) => this.loaded.get(e.id));
    const scenes = await Promise.all(recs.map((rec) => (!rec ? null : this.exporting ? this.load(rec) : rec.scene))); // (no rec: --only left it out, red fill)
    const times = new Map<string, Set<number>>();
    for (const sub of this.plan(t, dt, shutter, shutterOffsets(samples))) {
      for (const { entry, time } of layerEntries(sub)) {
        let set = times.get(entry.id);
        if (!set) times.set(entry.id, (set = new Set()));
        set.add(time);
      }
    }
    await Promise.all(on.map(async (entry, i) => {
      const s = scenes[i];
      if (!s?.prepare) return;
      try {
        await Promise.all([...(times.get(entry.id) ?? [])].map((x) => s.prepare!(x)));
      } catch (err) {
        throw this.exporting ? this.fail(entry, `prepare(${t})`, err) : err;
      }
    }));
    if (this.exporting) this.warmUp(on, t, dt, samples, shutter);
  }

  /**
   * Export (stills and video): the first time a scene is on screen after it loads, render the frame at t once, off
   * screen, with the frame's own sampling, and throw it away. So the frame itself is never the first a scene renders:
   * the GPU work a first render does once (programs, texture uploads and their mip chains, render targets) is done, and
   * the first frame of a session or a scene renders as any later render of the same time does (without it a few pixels
   * of `ex`'s first still differed by a level, run to run). The seek state (the engine's last time and each scene's) is
   * put back, so the frame renders exactly as it would have. Skipped while a stateful scene is on screen: it would step
   * twice.
   */
  private warmUp(entries: TimelineEntry[], t: number, dt: number, samples: number | AdaptiveSampling, shutter: number) {
    const recs = entries.map((e) => this.loaded.get(e.id)).filter((r): r is Loaded => !!r?.scene);
    if (recs.every((r) => r.warm) || recs.some((r) => r.scene!.stateful)) return;
    const lastT = this.lastT, seen = [...this.loaded.values()].map((r) => [r, r.lastT] as const);
    try {
      this.render(t, dt, false, samples, shutter);
    } finally {
      this.lastT = lastT;
      for (const [r, x] of seen) r.lastT = x;
    }
    for (const r of recs) r.warm = true;
  }

  /**
   * Export frames [round(from·fps), round(to·fps)) in order, awaiting `emit(n, k)` after frame n renders (k sub-frames:
   * the caller reads its pixels and sends them). In export (`exporting`):
   * - first every scene that owns a later frame of the range loads and is disposed again, one at a time, so a scene
   *   that cannot init fails the export before its first frame, not hours into it;
   * - a warm-up frame before the range makes the first frame sequential for stateful scenes. It is never sent, so it is
   *   best effort: its scenes may lack plate frames the range never shows;
   * - each scene loads just before its first frame (prepare) and is disposed after its last (releaseEnded), its plates
   *   with it, so the export holds only what is on screen.
   * Rejects on the first scene error. Resolves with a histogram: sub-frames per frame -> frames.
   */
  async exportFrames(o: { from: number; to: number; fps: number; samples?: number | AdaptiveSampling; shutter?: number }, emit: (n: number, k: number) => Promise<void> | void): Promise<Record<number, number>> {
    const { fps } = o, dt = 1 / fps, S = o.samples ?? 1, SH = o.shutter ?? 0.5;
    const n0 = Math.round(o.from * fps), n1 = Math.round(o.to * fps);
    // frame n is at n / fps (as ownedFrames counts it); n·dt can land an ulp early, in the scene before a cut exactly
    // on that frame's time
    const at = (n: number) => n / fps;
    if (this.exporting) {
      // (the scenes the first frame renders load for it at once, and fail just as early)
      const first = this.entriesAt(at(n0));
      for (const e of this.timeline) {
        // the frames a scene renders: its own, and those of the transitions into and out of it
        const tr = this.transitions ?? [];
        const { first: f0, last: f1 } = ownedFrames({ start: firstUse(e, tr), end: lastUse(e, tr) }, fps), rec = this.loaded.get(e.id);
        if (f0 > f1 || f0 >= n1 || f1 < n0 || first.includes(e)) continue;
        if (!rec) console.warn(`${e.id} is not loaded (--only): its frames in the range render as red fill`);
        else if (!rec.scene) {
          await this.load(rec);
          this.unload(rec);
        }
      }
    }
    if (n0 > 0) {
      // (adaptive sampling only runs stateless scenes: one sample is enough for the warm-up)
      const S0 = typeof S === 'number' ? S : 1, mark = this.errors.length;
      try {
        await this.prepare(at(n0 - 1), dt, S0, SH);
        this.render(at(n0 - 1), dt, false, S0, SH);
      } catch (err) {
        this.errors.splice(mark); // not an error of the export: the frame is not in it
        console.warn(`warm-up frame ${n0 - 1} skipped (it is not exported): ${(err as Error)?.message ?? err}`);
      }
      this.releaseEnded(at(n0));
    }
    const used: Record<number, number> = {};
    for (let n = n0; n < n1; n++) {
      await this.prepare(at(n), dt, S, SH);
      const k = this.render(at(n), dt, false, S, SH);
      used[k] = (used[k] ?? 0) + 1;
      await emit(n, k);
      this.releaseEnded(at(n + 1));
    }
    return used;
  }

  private frameFor(e: TimelineEntry, t: number, dt: number, seeked: boolean, preroll: boolean): Frame {
    const beat = this.audio.beatAt(t), bar = this.audio.barAt(t);
    return {
      t, dt, lt: t - e.start, p: (t - e.start) / (e.end - e.start), start: e.start, end: e.end, seeked, preroll,
      beat, bar, beatPhase: beat - Math.floor(beat), barPhase: bar - Math.floor(bar),
      a: this.audio.sample(t),
    };
  }

  /**
   * The transition's states for the frame at t, when t lies in one's window: shutterTaps with tapCount taps (at the
   * output's physical scale). Every sub-frame of the frame draws the transition with these same taps, so its motion is
   * blurred once, analytically, over the whole shutter, and the sub-frames sample only the scenes' own motion.
   */
  private framesTaps(t: number, dt: number, shutter: number): TransitionState[] | null {
    const tr = (this.transitions ?? []).find((x) => t >= x.start && t < x.end);
    return tr ? shutterTaps(tr, t, dt, shutter, tapCount(tr, t, dt, shutter, SCALE)) : null;
  }

  /**
   * Render song time t. `dt` is the nominal frame step (1/fps). A non-sequential t counts as a
   * seek: stateful scenes are reset and fast-forwarded.
   *
   * Motion blur (offline export; the preview uses 1 sample): `samples` > 1 renders that many sub-frames
   * spread evenly over `shutter` x dt around t and averages them before post-processing, which gives real
   * motion blur plus temporal anti-aliasing. With an AdaptiveSampling the count is chosen per frame:
   * sub-frames are added in nested steps (4, 12, 36 … each set evenly spread over the shutter, see
   * ternaryOffsets) until the estimated remaining error is below `tol` levels. Stepped copies of a moving
   * edge shrink as 1/count, so when a step changes the frame by e, what is left is about e/2
   * (e·(1/3 + 1/9 + …)). A still frame stops at 3 x min; a whip pan goes on until its streaks are
   * continuous instead of stepped copies.
   * Every sub-frame shows the entries on screen at t, each at its sub-frame's time held inside its own window
   * (shutterPlan): a frame never mixes the two sides of a cut, except inside a transition's window, where both its
   * scenes render (framePlan) and the transition's own motion is drawn from the frame's shutterTaps.
   * Returns the number of sub-frames used.
   */
  render(t: number, dt = 1 / FPS, toScreen = true, samples: number | AdaptiveSampling = 1, shutter = 0.5): number {
    const r = this.renderer;
    const seeked = this.lastT < 0 || t < this.lastT - 1e-6 || t - this.lastT > Math.max(0.25, dt * 4);
    this.lastT = t;
    let outTex: THREE.Texture;
    let post: PostParams = { ...DEFAULT_POST };
    let n = 1;
    const taps = this.framesTaps(t, dt, shutter);
    if (samples === 1) {
      SS_TAP.value = -1;
      ({ outTex, post } = this.composite(this.plan(t, dt, shutter, shutterOffsets(1))[0]!, dt, seeked, t, taps));
    } else {
      const adaptive = typeof samples !== 'number';
      let maxAdaptive = adaptive ? samples.max : 0;
      if (adaptive) {
        // sub-frames are rendered out of time order: fine for pure functions of t, not for scenes that integrate state
        // (a transition's two sides included)
        const on = this.entriesAt(t);
        const st = on.find((e) => this.loaded.get(e.id)?.scene?.stateful);
        if (st) throw new Error(`adaptive sampling needs stateless scenes; '${st.id}' is stateful (use a fixed --samples)`);
        for (const e of on) if (e.maxSamples) maxAdaptive = Math.min(maxAdaptive, e.maxSamples);
      }
      // shaders that supersample share their 4 taps across the sub-frames when every set holds a multiple
      // of 4 (rotated by k/4 so a tap doesn't always land in the same part of the shutter)
      const cycle = adaptive || samples % 4 === 0;
      // post parameters (shake, flash, zoom, fades, the HUD's paper mode) are read at one point of the shutter,
      // 1/8 of it after t: where the video was tuned (4 sub-frames, the third) and a point every adaptive set
      // includes. (A flash that starts between t and there shows at its peak on this frame, not one frame on.)
      const POST_U = 0.125;
      let nearest = Infinity;
      // what each sub-frame renders, per shutter offset (the cut-aware shutter, see shutterPlan)
      let plan: Layer[][] = [];
      // sub-frame k at shutter offset u (-0.5..0.5), summed into `into`; `step` = the sub-frame spacing
      const sub = (k: number, u: number, into: THREE.WebGLRenderTarget, step: number) => {
        SS_TAP.value = cycle ? (k + (k >> 2)) % 4 : -1;
        const res = this.composite(plan[k]!, step, seeked && k === 0, t, taps);
        this.accum.u.src!.value = res.outTex;
        this.accum.render(r, into);
        const d = Math.abs(u - POST_U);
        if (d < nearest - 1e-9 || (d < nearest + 1e-9 && u > POST_U)) { nearest = d; post = res.post; }
      };
      clearRT(r, this.sumRT, [0, 0, 0], 0);
      if (!adaptive) {
        n = samples;
        const u = shutterOffsets(samples);
        plan = this.plan(t, dt, shutter, u);
        for (let k = 0; k < n; k++) sub(k, u[k]!, this.sumRT, dt / n);
      } else {
        const { lo, hi } = adaptiveSteps(samples, maxAdaptive);
        const u = shutterOffsets({ ...samples, max: maxAdaptive });
        plan = this.plan(t, dt, shutter, u);
        n = 4 * 3 ** lo;
        this.lastErrors = [];
        for (let k = 0; k < n; k++) sub(k, u[k]!, this.sumRT, dt / n);
        for (let l = lo; l < hi; l++) {
          clearRT(r, this.newRT, [0, 0, 0], 0);
          for (let k = n; k < 3 * n; k++) sub(k, u[k]!, this.newRT, dt / (3 * n));
          const err = this.sampleError(n) / 2;
          this.lastErrors.push(err);
          this.comp.draw(r, this.newRT.texture, this.sumRT, { mode: 'add', opacity: 1, premult: false });
          n *= 3;
          if (err < samples.tol) break;
        }
      }
      SS_TAP.value = -1;
      this.comp.draw(r, this.sumRT.texture, this.avgRT, { mode: 'replace', opacity: 1 / n, premult: false });
      outTex = this.avgRT.texture;
    }
    this.lastSamples = n;
    const hudTex = this.hud.draw(t, { opacity: this.hudOff ? 0 : post.hud, frame: post.frame, paper: post.paper });
    this.post.render(r, outTex, hudTex, this.finalRT, post, t);
    this.lastPost = post;
    if (toScreen) {
      this.blit.u.src!.value = this.finalRT.texture;
      this.blit.render(r, null);
    }
    return n;
  }

  /**
   * How far the displayed frame (8-bit levels, worst block) moves when the 2n sub-frames summed in newRT
   * are merged with the n summed in sumRT. Stepped copies of a fast edge differ between the two
   * interleaved sets; a converged streak does not.
   */
  private sampleError(n: number) {
    const r = this.renderer;
    this.errPass.u.a!.value = this.sumRT.texture;
    this.errPass.u.b!.value = this.newRT.texture;
    this.errPass.u.invA!.value = 1 / n;
    this.errPass.u.invB!.value = 1 / (2 * n);
    this.errPass.render(r, this.errRT);
    this.maxPass.u.e!.value = this.errRT.texture;
    this.maxPass.render(r, this.maxRT);
    r.readRenderTargetPixels(this.maxRT, 0, 0, this.maxRT.width, this.maxRT.height, this.errBuf);
    let m = 0;
    for (let i = 0; i < this.errBuf.length; i += 4) m = Math.max(m, this.errBuf[i]!);
    return m;
  }

  /**
   * Render and composite one sub-frame into an HDR texture (no post): its layers (a framePlan sub-frame, in compositing
   * order). A scene renders into sceneRT. A transition renders its sides into trA and trB at their side times and draws
   * them through `taps` (the frame's) into trOut; its post overrides are the side the frame t is on. An overlay renders
   * into ovRT and is drawn ('normal', premultiplied) over what is below it into one of a ping-pong pair. `dt` is the
   * step handed to scenes (the frame step, or the sub-frame spacing; 0 for an entry held in its window, where no time
   * passes); `seeked` says time jumped before this call. A scene that throws (or is not loaded) fails the render in
   * export; the player fills it red and goes on. An entry --only left out is red fill either way.
   */
  private composite(layers: Layer[], dt: number, seeked: boolean, t: number, taps: TransitionState[] | null): { outTex: THREE.Texture; post: PostParams } {
    const r = this.renderer;
    let post: PostParams = { ...DEFAULT_POST };
    let outTex: THREE.Texture | null = null;
    let pp = 0;
    for (const l of layers) {
      if (l.kind === 'scene') {
        post = { ...post, ...this.renderEntry(l.at, this.sceneRT, dt, seeked) };
        outTex = this.sceneRT.texture;
      } else if (l.kind === 'transition') {
        const pa = this.renderEntry(l.a, this.trA, dt, seeked), pb = this.renderEntry(l.b, this.trB, dt, seeked);
        post = { ...post, ...(t >= l.tr.cut ? pb : pa) };
        this.trPass ??= new TransitionPass();
        this.trPass.render(r, this.trA.texture, this.trB.texture, taps ?? shutterTaps(l.tr, t, 0, 0, 1), this.trOut, { soft: l.tr.spec.soft });
        outTex = this.trOut.texture;
      } else {
        this.ovRT ??= makeRT();
        if (!this.ovPP.length) this.ovPP = [makeRT(W, H, { depthBuffer: false }), makeRT(W, H, { depthBuffer: false })];
        clearRT(r, this.ovRT, [0, 0, 0], 0);
        post = { ...post, ...this.renderEntry(l.at, this.ovRT, dt, seeked) };
        const dst = this.ovPP[pp]!;
        pp ^= 1;
        if (outTex) this.comp.draw(r, outTex, dst, { mode: 'replace', premult: false });
        else clearRT(r, dst, [0, 0, 0]);
        this.comp.draw(r, this.ovRT.texture, dst, { mode: 'normal', premult: false });
        outTex = dst.texture;
      }
    }
    if (!outTex) { clearRT(r, this.sceneRT, [0, 0, 0]); outTex = this.sceneRT.texture; }
    return { outTex, post };
  }

  /**
   * Render one entry at its time into `rt` (fast-forwarding a stateful scene after a seek), and return its post
   * overrides (the entry's defaults, then the scene's). Not loaded, or a throw: export fails, the player fills it red.
   */
  private renderEntry({ entry: e, time: t, held }: EntryAt, rt: THREE.WebGLRenderTarget, dt: number, seeked: boolean): PostOverrides {
    const r = this.renderer, rec = this.loaded.get(e.id);
    if (!rec?.scene) {
      if (this.exporting && rec) throw this.fail(e, `render(${t})`, new Error('not loaded: prepare(t) must be awaited before render(t)'));
      clearRT(r, rt, [0.25, 0.0, 0.0]);
      return {};
    }
    const s = rec.scene;
    // (sub-frames of one frame may step back within its shutter: not a seek)
    const sceneSeeked = seeked || rec.lastT < 0 || Math.abs(t - rec.lastT) > 0.25;
    let ov: PostOverrides | void = undefined;
    try {
      if (s.stateful && sceneSeeked) {
        s.reset();
        const from = Math.max(e.start, t - s.prerollMax);
        const step = 1 / FPS;
        let first = true;
        for (let pt = from; pt < t - step * 0.5; pt += step) {
          s.render(this.frameFor(e, pt, first ? 0 : step, first, true), rt);
          first = false;
        }
      }
      ov = s.render(this.frameFor(e, t, sceneSeeked || held ? 0 : dt, sceneSeeked && !s.stateful, false), rt);
    } catch (err) {
      if (this.exporting) throw this.fail(e, `render(${t})`, err);
      console.error(`scene ${e.id} render error`, err);
      clearRT(r, rt, [0.25, 0.0, 0.0]);
    }
    rec.lastT = t;
    return { ...(e.post ?? {}), ...(ov ?? {}) };
  }

  /** RGBA8 pixels of the last rendered frame (bottom-up rows), PW x PH. */
  readPixels(buf?: Uint8Array) {
    const out = buf ?? new Uint8Array(PW * PH * 4);
    this.renderer.readRenderTargetPixels(this.finalRT, 0, 0, PW, PH, out);
    return out;
  }

  /**
   * Same pixels as readPixels(), read through a pixel-pack buffer and a fence instead of a blocking
   * readPixels: several times faster in Chrome (~15 ms instead of ~40 ms at 1080p, ~150 ms at 4K).
   */
  async readPixelsAsync(buf?: Uint8Array) {
    const out = buf ?? new Uint8Array(PW * PH * 4);
    await this.renderer.readRenderTargetPixelsAsync(this.finalRT, 0, 0, PW, PH, out);
    return out;
  }
}
