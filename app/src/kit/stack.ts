// Stack: one shot made of several blocks layered, bottom first: a background under type, dust over a title, a device
// over a mesh gradient. Each layer is any scene (a kit block, a film's own) with its own params; it renders into the
// Stack's scratch target at its own time and is composited over the layers below it: premultiplied, as the engine
// composites overlays, so a 2D block with `background: 'none'` (and a background with 'none') lands over what is under
// it by its own alpha.
//
//   { id: 'open', scene: Stack, length: { bars: 2 }, params: { layers: [
//     { scene: Aurora, params: { pulse: 'downbeat' } },
//     { scene: Particles, params: { background: 'none', intensity: 0.6 }, blend: 'add' },
//     { scene: TitleCard, params: { background: 'none', title: 'Hello.' }, start: 0.4 },
//   ] } }
//
// Params:
//   layers            the layers, bottom first: { scene, params?, blend?, opacity?, start?, end?, offset?, fade?, post? }
//     scene           a Scene class, or () => import('./scenes/x') (its default export)
//     params          the layer's own params (it also gets the shot's id as `shot`, so sync 'vo' finds the shot's words).
//                     Every layer above the first defaults to `background: 'none'`: a TitleCard over an Aurora is type
//                     over the aurora, not over a fresh bg
//     blend 'normal'  'normal' | 'add' | 'screen' | 'multiply'
//     opacity 1       0..1
//     start, end      when it shows, s from the shot's start (end < 0: s before the shot's end); default the whole shot.
//                     The layer's own window: its blocks time their reveals and exits from it
//     offset 0        s added to the layer's clock (it renders t + offset)
//     fade 0          s it fades in after `start` and out before `end` (only the edges given)
//     post true       whether its post overrides count (merged bottom to top)
//   background 'theme' what is under the first layer (common.ts; 'none': transparent)
//
// The Stack can render as far before and past its window as every layer can (its handles: the smallest of theirs), is
// stateful if a layer is, and passes prepare() on to the layers on screen.
import type * as THREE from 'three';
import { makeRT, clearRT } from '../engine/gl';
import { loaderOf, type SceneSource } from '../engine/film';
import { Scene, type Frame, type PostOverrides, type SceneCtx } from '../engine/scene';
import type { Handles } from '../engine/transition';
import { clearBackground, type Background } from './common';
import { smoothstep } from '../engine/util';

export type StackBlend = 'normal' | 'add' | 'screen' | 'multiply';

export interface StackLayer {
  scene: SceneSource;
  params?: Record<string, unknown>;
  blend?: StackBlend;
  opacity?: number;
  start?: number;
  end?: number;
  offset?: number;
  fade?: number;
  post?: boolean;
}

const BLENDS: readonly StackBlend[] = ['normal', 'add', 'screen', 'multiply'];

/** A layer's window in film time: [start, end), each edge open (±Infinity) when the layer leaves it to the shot. */
export interface LayerWindow { start: number; end: number; open: { start: boolean; end: boolean } }

/** Checks a Stack's `layers` param; throws naming the shot, the layer and the problem. */
export function checkLayers(layers: unknown, shot: string, shotLength = Infinity): StackLayer[] {
  if (!Array.isArray(layers) || layers.length === 0) throw new Error(`shot ${shot}: Stack needs \`layers\`, a non-empty array`);
  return layers.map((l, i) => {
    const at = `shot ${shot}: Stack layer ${i}`;
    if (!l || typeof l !== 'object') throw new Error(`${at} is not an object`);
    const L = l as StackLayer;
    if (typeof L.scene !== 'function') throw new Error(`${at}: \`scene\` is a Scene class or () => import(...)`);
    if (L.params !== undefined && (typeof L.params !== 'object' || L.params === null || Array.isArray(L.params))) throw new Error(`${at}: \`params\` is an object`);
    if (L.blend !== undefined && !BLENDS.includes(L.blend)) throw new Error(`${at}: blend is ${BLENDS.join(' | ')}, got '${L.blend}'`);
    for (const k of ['opacity', 'start', 'end', 'offset', 'fade'] as const) {
      const v = L[k];
      if (v !== undefined && !(typeof v === 'number' && Number.isFinite(v))) throw new Error(`${at}: ${k} is a number, got ${JSON.stringify(v)}`);
    }
    if (L.opacity !== undefined && (L.opacity < 0 || L.opacity > 1)) throw new Error(`${at}: opacity is 0..1, got ${L.opacity}`);
    if (L.fade !== undefined && L.fade < 0) throw new Error(`${at}: fade is >= 0, got ${L.fade}`);
    if (L.start !== undefined && L.start < 0) throw new Error(`${at}: start is >= 0 (s from the shot's start), got ${L.start}`);
    const w = layerWindow(L, 0, shotLength);
    if (!(w.end > w.start)) throw new Error(`${at}: its window [${L.start ?? 0}, ${L.end ?? 'end'}) is empty`);
    return L;
  });
}

/** A layer's window for a shot over [start, end) (film s). */
export function layerWindow(l: Pick<StackLayer, 'start' | 'end'>, start: number, end: number): LayerWindow {
  const s = start + (l.start ?? 0);
  const e = l.end === undefined ? end : l.end < 0 ? end + l.end : start + l.end;
  return { start: s, end: e, open: { start: l.start === undefined, end: l.end === undefined } };
}

/**
 * Whether a layer shows at film time t, and its opacity there (its own times its fade). An open edge (the layer runs
 * with the shot) never cuts it, so the layer renders into the Stack's handles as the shot does.
 */
export function layerAlpha(l: Pick<StackLayer, 'opacity' | 'fade'>, w: LayerWindow, t: number): number {
  if ((!w.open.start && t < w.start) || (!w.open.end && t >= w.end)) return 0;
  const f = l.fade ?? 0;
  let a = l.opacity ?? 1;
  if (f > 0 && !w.open.start) a *= smoothstep(w.start, w.start + f, t);
  if (f > 0 && !w.open.end) a *= 1 - smoothstep(w.end - f, w.end, t);
  return a;
}

/** The params a layer's scene gets: the shot's id and number, `background: 'none'` above the first layer, its own. */
export function layerParams(l: Pick<StackLayer, 'params'>, i: number, shot: string, n?: unknown): Record<string, unknown> {
  return { shot, ...(n !== undefined ? { n } : {}), ...(i > 0 ? { background: 'none' } : {}), ...(l.params ?? {}) };
}

/** The Stack's handles: the smallest of its layers'. */
export function stackHandles(hs: readonly Handles[]): Handles {
  return hs.reduce((m, h) => ({ head: Math.min(m.head, h.head), tail: Math.min(m.tail, h.tail) }), { head: Infinity, tail: Infinity });
}

/** The frame a layer renders at film time t: its own clock (t + offset) in its own window, the grid read there. */
export function layerFrame(f: Frame, w: LayerWindow, offset: number, grid: { beatAt(t: number): number; barAt(t: number): number; beatsPerBar: number; sample?: (t: number) => Frame['a'] }): Frame {
  if (offset === 0) return { ...f, lt: f.t - w.start, p: (f.t - w.start) / (w.end - w.start), start: w.start, end: w.end };
  const t = f.t + offset, start = w.start + offset, end = w.end + offset;
  const beat = grid.beatAt(t), bar = grid.barAt(t);
  return {
    ...f, t, lt: t - start, p: (t - start) / (end - start), start, end,
    beat, bar, beatPhase: beat - Math.floor(beat), barPhase: bar - Math.floor(bar), a: grid.sample ? grid.sample(t) : f.a,
  };
}

interface Live { spec: StackLayer; win: LayerWindow; scene: Scene }

export class Stack extends Scene {
  private layers: Live[] = [];
  private scratch: THREE.WebGLRenderTarget | null = null;

  override async init() {
    const { ctx } = this;
    const specs = checkLayers(ctx.params.layers, ctx.id, ctx.end - ctx.start);
    const shot = (ctx.params.shot as string | undefined) ?? ctx.id;
    try {
      for (const [i, spec] of specs.entries()) {
        const win = layerWindow(spec, ctx.start, ctx.end);
        const off = spec.offset ?? 0;
        const mod = await loaderOf(spec.scene)();
        const child: SceneCtx = {
          ...ctx, id: `${ctx.id}[${i}]`, params: layerParams(spec, i, shot, ctx.params.n),
          // its own window, on its own clock (an open edge is the shot's)
          start: win.start + off, end: win.end + off,
        };
        const scene = new mod.default(child);
        this.layers.push({ spec, win, scene });
        await scene.init();
      }
    } catch (err) {
      try {
        this.dispose();
      } catch {
        // half built: a layer's dispose may trip on what its init never made
      }
      throw err;
    }
    this.handles = stackHandles(this.layers.map((l) => l.scene.handles));
    this.stateful = this.layers.some((l) => l.scene.stateful);
    this.prerollMax = Math.max(0, ...this.layers.map((l) => (l.scene.stateful ? l.scene.prerollMax : 0)));
    this.scratch = makeRT();
  }

  override async prepare(t: number) {
    await Promise.all(this.layers.map((l) => (l.scene.prepare && layerAlpha(l.spec, l.win, t) > 0 ? l.scene.prepare(t + (l.spec.offset ?? 0)) : undefined)));
  }

  override reset() {
    for (const l of this.layers) l.scene.reset();
  }

  render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides | void {
    const { renderer, comp, audio } = this.ctx;
    clearBackground(renderer, out, (this.ctx.params.background as Background | undefined) ?? 'theme');
    let post: PostOverrides = {};
    for (const l of this.layers) {
      const a = layerAlpha(l.spec, l.win, f.t);
      // a stateful layer steps on every frame, shown or not
      if (a <= 0.001 && !l.scene.stateful) continue;
      clearRT(renderer, this.scratch!, [0, 0, 0], 0);
      const ov = l.scene.render(layerFrame(f, l.win, l.spec.offset ?? 0, audio), this.scratch!);
      if (ov && l.spec.post !== false) post = { ...post, ...ov };
      if (a <= 0.001) continue;
      // premultiplied over what is below (the engine's overlays: 'normal', premult off), in light
      comp.draw(renderer, this.scratch!.texture, out, { mode: l.spec.blend ?? 'normal', opacity: a, premult: false, space: 'linear' });
    }
    return post;
  }

  override dispose() {
    for (const l of this.layers) l.scene.dispose();
    this.layers = [];
    this.scratch?.dispose();
    this.scratch = null;
  }
}

export default Stack;
