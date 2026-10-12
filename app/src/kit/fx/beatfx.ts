// BeatFx: beat-driven camera effects as an overlay (film.ts `overlays`). It draws nothing (its target is cleared to alpha
// 0), or a flash frame in a role's light, and returns post overrides: a zoom punch, a shake, an fg flash, an exposure
// pump and letterbox bars, each on hits of the film's grid or at given times, in the house motion language (beat.ts).
// Overlays' overrides are merged after the scene's, so while one of its effects is on it owns that post key (zoom,
// shake, flash, exposure, letterbox); between hits it returns nothing for it and the shot's own value holds.
//
// Params (each effect: absent or false off, true its defaults, or an object of options):
//   punch    zoom punch: { on 'beat', every 1, amount 0.035 } (the house spring's kick, landing on the hit)
//   shake    camera shake: { on 'downbeat', every 1, amount 14 (reference px), decay 0.25, freq 22, seed 1 }
//   flash    a flash: { on 'downbeat', every 1, amount 0.3, decay 0.16, color 'fg' } ('fg': the post's additive flash;
//            any other role or #hex: a frame of that colour's light drawn by the overlay, an accent wash that never blooms)
//   pump     exposure pump: { on 'beat', every 1, amount 0.12 (negative ducks), decay 0.25 }
//   bars     letterbox: { aspect 2.39, in 0, out } (TimeRefs: bars spring in at `in` and out at `out`)
//   from, to the window hits fall in (TimeRefs from the overlay's start; default its whole window)
// `on` is 'beat' | 'downbeat' | 'bar' (= 'downbeat') | 'backbeat' (beats 2 and 4) or a list of TimeRefs (s from the
// overlay's start, { beat }, { bar }). Every value is a pure function of time: any frame renders alone, in any order.
import type * as THREE from 'three';
import { Scene, type Frame, type PostOverrides } from '../../engine/scene';
import { clearRT } from '../../engine/gl';
import { lin } from '../../engine/palette';
import { resolveTime, type TimeRef } from '../text/fx';
import { bars, flash, hitEnv, lastHit, pump, punch, shake, shakeCover, type HitOpts, type On } from './beat';

type When = Exclude<On, number[]> | TimeRef[];
interface EffectOpts { on?: When; every?: number; amount?: number; decay?: number }
type Effect<T = object> = boolean | (EffectOpts & T);

export class BeatFx extends Scene {
  /** Pure functions of time: a 'run' transition may render it past its window. */
  override handles = { head: 0.5, tail: 0.5 };
  private from = -Infinity;
  private to = Infinity;

  override init() {
    const { start, end, audio } = this.ctx;
    const from = this.ctx.params.from as TimeRef | undefined, to = this.ctx.params.to as TimeRef | undefined;
    this.from = from !== undefined ? resolveTime(from, start, audio) : start;
    this.to = to !== undefined ? resolveTime(to, start, audio) : end;
  }

  /** An effect's options resolved (null: off): its hits' times, the grid, the window. */
  private opts<T extends object>(key: string, fallbackOn: Exclude<On, number[]>): (HitOpts & T) | null {
    const v = this.ctx.params[key] as Effect<T> | undefined;
    if (!v) return null;
    const o = (v === true ? {} : v) as EffectOpts & T;
    const on: On = Array.isArray(o.on) ? o.on.map((r) => resolveTime(r, this.ctx.start, this.ctx.audio)) : (o.on ?? fallbackOn);
    return { ...o, on, grid: this.ctx.audio, from: this.from, to: this.to } as HitOpts & T;
  }

  render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides {
    const post: PostOverrides = {};
    const p = this.opts('punch', 'beat');
    let zoom = p ? punch(f, p) : 1;
    const s = this.opts<{ freq?: number; seed?: number }>('shake', 'downbeat');
    if (s) {
      const [x, y] = shake(f, s);
      if (x !== 0 || y !== 0) {
        post.shake = [x, y];
        zoom *= shakeCover(Math.hypot(x, y));
      }
    }
    if (zoom > 1 + 1e-6) post.zoom = zoom;
    const fl = this.opts<{ color?: string }>('flash', 'downbeat');
    let frame: [number, number, number] | null = null;
    if (fl) {
      const k = flash(f, fl);
      const color = fl.color ?? 'fg';
      if (k > 1e-4) {
        if (color === 'fg') post.flash = k;
        else {
          // a frame of the colour's light, its brightest channel at k (added: the overlay is drawn premultiplied)
          const c = lin(color), m = Math.max(c[0], c[1], c[2], 1e-6);
          frame = [(c[0] * k) / m, (c[1] * k) / m, (c[2] * k) / m];
        }
      }
    }
    const pu = this.opts('pump', 'beat');
    if (pu && hitEnv(f.t - lastHit(f.t, pu), pu.decay ?? 0.25) > 1e-4) post.exposure = pump(f, pu);
    const b = this.ctx.params.bars as Effect<{ aspect?: number; in?: TimeRef; out?: TimeRef }> | undefined;
    if (b) {
      const o = b === true ? {} : b, { start, audio } = this.ctx;
      post.letterbox = bars(f, { aspect: o.aspect, in: resolveTime(o.in ?? 0, start, audio), out: o.out !== undefined ? resolveTime(o.out, start, audio) : undefined });
    }
    // transparent, or the flash frame as light (alpha 0: premultiplied 'normal' adds it)
    clearRT(this.ctx.renderer, out, frame ?? [0, 0, 0], 0);
    return post;
  }
}

export default BeatFx;
