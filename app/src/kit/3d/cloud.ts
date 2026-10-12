// GlyphCloud: a field of floating glyphs (engine/glyphs.ts: SDF cells, crisp up close, out of focus far and near) that
// flows past the camera as it pushes through, a few of them accent sparks that glow and twinkle on the beat; on
// `resolveAt` glyphs fly out of the field into a word or a number, morphing into its characters as they land, and the
// field falls back behind it.
//
// Params (all optional):
//   count 1400         glyphs in the field; seed 1 (where they are, which glyph each is)
//   chars              what the field is made of (default hex digits and code punctuation)
//   size 30            a glyph's em at the focus plane (px); depth 9 (world units the field runs back)
//   flow 0.45          how fast the field drifts toward the camera (world units per s; 0 holds it)
//   sparkle 0.035      the fraction of glyphs that are accent sparks; sparkleColor 'accent' | 'accent2'
//   resolve            a word or number the glyphs fly into; resolveAt ({ beat: 4 } by default), resolveSize 170 (px),
//                      resolveColor 'fg' (a role or #hex; an accent glows), resolveStagger 0.018 (s between glyphs)
//   weight 500         the mono face's weight
//   camera 'push', fov 34, fstop 2.0 (focus on the word's plane), and every Scene3D param
import * as THREE from 'three';
import { GlyphActors, GlyphAtlas } from '../../engine/glyphs';
import { F } from '../../engine/type';
import { W, H } from '../../engine/gl';
import { glow } from '../../engine/look';
import { lin } from '../../engine/palette';
import { onBeat, slam } from '../../engine/motion';
import { clamp, hash, lerp, mod, prog, smoothstep, ease } from '../../engine/util';
import type { TimeRef } from '../text/fx';
import { Scene3D, type Frame } from './scene3d';
import { basis } from './camera';

const DEFAULT_CHARS = '0123456789abcdef{}[]()<>=+-*/#$%&;:.';
/** The focus plane is FRAME_UNITS tall (as Hero3D's). */
const FRAME_UNITS = 2.4;

interface Seed { x: number; y: number; z: number; ch: number; b: number; ph: number; spark: boolean }

export class GlyphCloud extends Scene3D {
  protected override defaults: Record<string, unknown> = { camera: 'push', fov: 34, fstop: 2.0, az: 0, el: 0, cameraAmount: 1.4 };
  private atlas!: GlyphAtlas;
  private actors!: GlyphActors;
  private seeds: Seed[] = [];
  private glyphIdx: number[] = [];
  private target: { idx: number; x: number; from: number }[] = [];
  private em = 0.04;
  private wordEm = 0.2;
  private half = { w: 1, h: 1 };
  private resolveT = Infinity;

  protected build() {
    const chars = Array.from(this.p('chars', DEFAULT_CHARS)).filter((c) => !/\s/u.test(c));
    if (!chars.length) throw new Error(`shot ${this.ctx.id}: GlyphCloud's chars are empty`);
    const word = String(this.p<string | number>('resolve', ''));
    const fam = F.mono(this.p('weight', 500));
    this.atlas = this.own(new GlyphAtlas([...chars, ...Array.from(word)], fam));
    this.glyphIdx = chars.map((c) => this.atlas.of(c));
    const n = Math.max(1, Math.round(this.p('count', 1400)));
    this.actors = this.own(new GlyphActors(n, this.atlas));
    this.stage.scene.add(this.actors.mesh);
    const ppu = H / FRAME_UNITS, u = this.u;
    this.em = (this.p('size', 30) * u) / ppu;
    this.half = { w: (FRAME_UNITS * W) / H / 2, h: FRAME_UNITS / 2 };
    const seed = this.p('seed', 1), spark = this.p('sparkle', 0.035);
    for (let i = 0; i < n; i++) {
      const r = (k: number) => hash(seed, i, k);
      this.seeds.push({ x: r(1) * 2 - 1, y: r(2) * 2 - 1, z: r(3), ch: Math.floor(r(4) * chars.length), b: 0.25 + 0.75 * r(5) ** 2, ph: r(6) * 6.283, spark: r(7) < spark });
    }
    // the word: mono cells 0.6 em apart, centred on the focus plane; each glyph taken from the field, spread through it
    const glyphs = Array.from(word);
    if (glyphs.length) {
      this.wordEm = Math.min((this.p('resolveSize', 170) * u) / ppu, (0.86 * 2 * this.half.w) / (0.6 * glyphs.length));
      this.resolveT = this.at(this.p<TimeRef>('resolveAt', { beat: 4 }));
      const x0 = (-0.6 * glyphs.length * this.wordEm) / 2;
      const stride = Math.max(1, Math.floor(n / glyphs.length));
      glyphs.forEach((ch, j) => {
        if (/\s/u.test(ch)) return;
        this.target.push({ idx: Math.min(n - 1, j * stride + (stride >> 1)), x: x0 + 0.6 * j * this.wordEm, from: this.atlas.of(ch) });
      });
    }
    const dist = this.half.h / Math.tan((this.p('fov', 34) * Math.PI) / 360);
    this.frame({ centre: [0, 0, 0], w: 2 * this.half.w, h: 2 * this.half.h, dist });
  }

  /** A field glyph's place at shot time lt: drifting toward the camera, wrapping at the field's ends. */
  private place(s: Seed, lt: number, out: THREE.Vector3): number {
    const depth = this.p('depth', 9), near = this.base.dist * 0.82;
    const span = depth + near;
    const z = -depth + mod(s.z * span + this.p('flow', 0.45) * lt, span);
    // the field widens with distance so it fills the frame at every depth
    const spread = 1.25 * (this.base.dist - z) / this.base.dist;
    out.set(s.x * this.half.w * spread + 0.03 * Math.sin(0.4 * lt + s.ph), s.y * this.half.h * spread + 0.03 * Math.cos(0.33 * lt + s.ph), z);
    // fade in at the back, out just before the camera
    return smoothstep(-depth, -depth + 1.5, z) * (1 - smoothstep(near - 1.2, near - 0.2, z));
  }

  protected update(f: Frame): THREE.Vector3 {
    const { right, up } = basis(this.base.az, this.base.el);
    const R = new THREE.Vector3(...right), U = new THREE.Vector3(...up);
    const lt = f.lt, t = f.t, A = this.actors;
    const fg = lin('fgDim'), sparkKey = this.p<'accent' | 'accent2'>('sparkleColor', 'accent');
    const beat = onBeat(f, 0.35);
    const resolveColor = this.p<string>('resolveColor', 'fg');
    const rc = resolveColor === 'accent' || resolveColor === 'accent2' ? glow(resolveColor, 0.45 * this.glowLevel) : lin(resolveColor);
    const settled = this.target.length ? prog(t, this.resolveT, this.resolveT + 0.8, ease.inOutCubic) : 0;
    const taken = new Map(this.target.map((x, j) => [x.idx, j]));
    const pos = new THREE.Vector3(), origin = new THREE.Vector3();
    A.begin();
    this.seeds.forEach((s, i) => {
      const fade = this.place(s, lt, pos);
      const j = taken.get(i);
      const g = this.glyphIdx[s.ch]!;
      let em = this.em, col: [number, number, number], a = fade * (1 - 0.45 * settled);
      let glyph: [number, number, number, number] = [g, -1, 0, 0];
      if (s.spark) {
        const tw = 0.55 + 0.45 * Math.sin(2.1 * lt + s.ph * 3);
        col = glow(sparkKey, this.glowLevel * (0.45 + 0.4 * tw + 0.5 * beat));
      } else col = [fg[0] * s.b, fg[1] * s.b, fg[2] * s.b];
      // the cell's origin is its left end on the baseline: a field glyph is centred on its point
      origin.copy(pos).addScaledVector(R, -0.3 * em).addScaledVector(U, -0.36 * em);
      if (j !== undefined) {
        const T = this.target[j]!;
        const k = slam(t, this.resolveT + j * this.p('resolveStagger', 0.018), { freq: 3.2, damping: 0.78 });
        if (k > 0) {
          origin.lerp(new THREE.Vector3(T.x, -0.36 * this.wordEm, 0), k);
          em = lerp(em, this.wordEm, clamp(k));
          col = [lerp(col[0], rc[0], clamp(k)), lerp(col[1], rc[1], clamp(k)), lerp(col[2], rc[2], clamp(k))];
          a = lerp(fade, 1, clamp(k * 1.5));
          glyph = [g, T.from, clamp(k * 1.25), 2];
        }
      }
      if (a <= 0.002) return;
      A.add({ origin: origin.clone(), right: R.clone().multiplyScalar(em), up: U.clone().multiplyScalar(em), glyph, color: [col[0], col[1], col[2], a] });
    });
    A.end();
    return new THREE.Vector3(0, 0, 0);
  }
}

export default GlyphCloud;
