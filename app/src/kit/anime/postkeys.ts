// PostKeys: the frame's post parameters animated over a shot, drawing nothing of its own. Put it in a Stack over a
// picture, or play it as an overlay over several shots: an impact frame (an inverted strobe, a white flash, a shake),
// letterbox bars sliding in, a grade warming as the rain stops.
//
// Params: any number post parameter (post.ts PostParams: exposure, flash, invert, zoom, saturation, contrast, warmth,
// tint, lift, letterbox, vignette, grain, fade, bloom, ...) as keys over the entry's time:
//   flash: [[0, 1.4], [0.12, 0]]                 [s, value] pairs, s from the entry's start; eased 'inOutSine' between
//   invert: { keys: [[0, 1], [0.08, 0]], step: true }   or with options: `step` holds each key until the next
//                                                (strobes), `ease` names another easing (engine util.ts ease)
// and two of its own:
//   shake: [[0, 24], [0.5, 0]]                   px of shake (a fresh random offset every frame, like a hand-drawn
//                                                shake), keyed like the rest
//   letterboxIn: [t0, t1, aspect]                the bars slide from nothing (t0) to `aspect` (t1); letterboxOut:
//                                                [t0, t1] slides them back out (letterbox keys do it by hand)
import * as THREE from 'three';
import { Scene, type Frame, type PostOverrides, type SceneCtx } from '../../engine/scene';
import { clearRT, H, W } from '../../engine/gl';
import { FPS } from '../../engine/config';
import { ease, hash } from '../../engine/util';
import { letterboxAspect } from '../../engine/looks';
import type { Handles } from '../../engine/transition';

export type Keys = [number, number][];
export interface Track { keys: Keys; step?: boolean; ease?: keyof typeof ease | 'inOutSine' }

const inOutSine = (t: number) => 0.5 - 0.5 * Math.cos(Math.PI * t);

/** A track's value at time t (s from the entry's start): held before its first key and after its last. */
export function trackAt(tr: Keys | Track, t: number): number {
  const o: Track = Array.isArray(tr) ? { keys: tr } : tr;
  const k = [...o.keys].sort((a, b) => a[0] - b[0]);
  if (!k.length) return 0;
  if (t <= k[0]![0]) return k[0]![1];
  for (let i = 1; i < k.length; i++) {
    const [t0, v0] = k[i - 1]!, [t1, v1] = k[i]!;
    if (t < t1) {
      if (o.step) return v0;
      const x = (t - t0) / Math.max(1e-9, t1 - t0);
      const fn = o.ease === undefined || o.ease === 'inOutSine' ? inOutSine : ease[o.ease];
      return v0 + (v1 - v0) * fn(x);
    }
  }
  return k[k.length - 1]![1];
}

/** The bar a letterbox `aspect` covers, as a share of the frame's height (0 for none). */
const barOf = (aspect: number) => (aspect > 0 ? Math.max(0, (H - W / aspect) / 2) / H : 0);

const OWN = new Set(['shake', 'letterboxIn', 'letterboxOut']);

export class PostKeys extends Scene {
  override handles: Handles = { head: 1, tail: 1 };
  constructor(ctx: SceneCtx) {
    super(ctx);
  }

  render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides | void {
    clearRT(this.ctx.renderer, out, [0, 0, 0], 0);
    // every sub-frame of a frame gets the frame's values: a strobe or a shake never smears across the shutter
    const frame = Math.round(f.t * FPS);
    const lt = frame / FPS - this.ctx.start;
    const post: Record<string, unknown> = {};
    for (const [key, v] of Object.entries(this.ctx.params)) {
      if (OWN.has(key) || v === null || typeof v !== 'object') continue;
      if (Array.isArray(v) && !Array.isArray(v[0])) continue;   // not a key list (shot, n, ...)
      post[key] = trackAt(v as Keys | Track, lt);
    }
    const shake = this.ctx.params.shake as Keys | Track | undefined;
    if (shake) {
      const a = trackAt(shake, lt);
      if (a > 0) post.shake = [(hash(frame * 1.7 + 3) * 2 - 1) * a, (hash(frame * 2.3 + 11) * 2 - 1) * a];
    }
    const li = this.ctx.params.letterboxIn as [number, number, number] | undefined;
    const lo = this.ctx.params.letterboxOut as [number, number] | undefined;
    if (li || lo) {
      let bar = 0;
      if (li) bar = barOf(li[2]) * inOutSine(Math.min(1, Math.max(0, (lt - li[0]) / Math.max(1e-6, li[1] - li[0]))));
      if (lo) bar *= 1 - inOutSine(Math.min(1, Math.max(0, (lt - lo[0]) / Math.max(1e-6, lo[1] - lo[0]))));
      post.letterbox = bar > 1e-4 ? letterboxAspect(bar, W, H) : 0;
    }
    return post as PostOverrides;
  }
}

export default PostKeys;
