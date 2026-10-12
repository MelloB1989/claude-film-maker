// The transition's compositing pass: two scenes' HDR frames (A and B) into one, through the transition's states over the
// shutter (transition.ts shutterTaps). One full-screen pass: per sample it places A and B by their transforms, shows ink
// where neither covers the pixel, weighs them (wB, or match's luma key on A's display value), dips toward ink, and
// averages. Every output is a convex mix of A, B and ink, so it never brightens anything: bone stays under the bloom.
// The effects kinds (wipe, iris, slide, spin, flash, glitch) draw with a program of their own (fxFrag, below), so the
// original kinds render exactly as they always have.
import * as THREE from 'three';
import { FSPass, W, H } from './gl';
import { LIN, lin } from './palette';
import { SHOULDER_GLSL } from './post';
import { glow } from './look';
import {
  MAX_FX_TAPS, MAX_TAPS, SUB_TAPS, irisTrack, isFxKind, pairSeed, wipeTrack,
  type TransitionEntry, type TransitionKind, type TransitionState,
} from './transition';

const frag = () => /* glsl */ `
uniform sampler2D A; uniform sampler2D B;
uniform vec4 taps[${2 * MAX_TAPS}];   // per tap: (a.tx, a.ty, a.s, wB), (b.tx, b.ty, b.s, ink or match threshold)
uniform int n;                        // taps in use
uniform bool isMatch;                 // the .w of the second vec4 is match's threshold (else the dip toward ink)
uniform vec2 cA; uniform vec2 cB;     // the transforms' centres, logical px
uniform float soft;
uniform vec3 ink;
${SHOULDER_GLSL}
const vec2 FR = vec2(${W}.0, ${H}.0);

// a picture placed by (tx, ty, s) about c, at logical px p (+y down): its colour, and whether it covers p
vec3 placed(sampler2D t, vec2 p, vec3 x, vec2 c, out float cov) {
  vec2 q = c + (p - x.xy - c) / x.z;
  cov = (q.x >= 0.0 && q.x <= FR.x && q.y >= 0.0 && q.y <= FR.y) ? 1.0 : 0.0;
  return cov > 0.0 ? texture(t, vec2(q.x / FR.x, 1.0 - q.y / FR.y)).rgb : ink;
}

vec3 shade(vec2 p, vec4 s0, vec4 s1) {
  float ca, cb;
  vec3 a = placed(A, p, s0.xyz, cA, ca);
  vec3 b = placed(B, p, s1.xyz, cB, cb);
  float w = s0.w;
  if (isMatch) {
    // B's weight: smoothstep(threshold − soft, threshold + soft, luma of A as displayed)
    float l = dot(toSRGB(sat(shoulder(max(a, 0.0)))), vec3(0.2126, 0.7152, 0.0722));
    w = smoothstep(s1.w - soft, s1.w + soft, l);
  }
  // a side that does not cover the pixel gives way to one that does (a whip's two pictures abut); neither: ink
  float wa = (1.0 - w) * ca, wb = w * cb;
  vec3 c = wa + wb > 0.0 ? (a * wa + b * wb) / (wa + wb) : (ca > 0.0 ? a : cb > 0.0 ? b : ink);
  return isMatch ? c : mix(c, ink, s1.w);
}

void main() {
  vec2 p = vec2(vUv.x, 1.0 - vUv.y) * FR;
  vec3 sum = vec3(0.0);
  if (n <= 1) sum = shade(p, taps[0], taps[1]);
  else {
    for (int k = 0; k < ${MAX_TAPS - 1}; k++) {
      if (k >= n - 1) break;
      vec4 a0 = taps[2 * k], a1 = taps[2 * k + 1], b0 = taps[2 * k + 2], b1 = taps[2 * k + 3];
      for (int j = 0; j < ${SUB_TAPS}; j++) {
        float f = (float(j) + 0.5) / ${SUB_TAPS}.0;
        sum += shade(p, mix(a0, b0, f), mix(a1, b1, f));
      }
    }
    sum /= float((n - 1) * ${SUB_TAPS});
  }
#if defined(KIND_WIPE) || defined(KIND_IRIS)
  // the edge line's core: a crisp 2 px line where the edge is at the frame's own time. Streaked over the shutter like
  // the rest, a fast edge's thin line smears into a dim bar a couple of hundred px wide; a light that leads the reveal
  // reads as one, sharp, with its spill trailing.
  if (edgeNow.y > 0.0) {
#ifdef KIND_WIPE
    float x = dot(p, dir) - mix(track.x, track.y, edgeNow.x);
#else
    float x = length(p - center) - mix(track.x, track.y, edgeNow.x);
#endif
    sum += edgeLight * edgeNow.y * exp(-x * x / 2.0);
  }
#endif
  fragColor = vec4(sum, 1.0);
}`;

// The effects kinds (transition.ts FX_KINDS): one program per kind, built on first use, with three vec4 per tap in the
// same uniform array: (a.tx, a.ty, a.s, a.r), (b.tx, b.ty, b.s, b.r), (wB, P, Q, 0), P and Q by kind: wipe and iris the
// edge's progress and its light, slide A's dim and B's shadow on it, flash its level, glitch its strength and frame.
// Each is a convex mix of A, B and ink but for the light it means to add: an edge line in glow('accent' | 'accent2'),
// a flash in its colour's light.
const fxFrag = (kind: TransitionKind) => /* glsl */ `
#define KIND_${kind.toUpperCase()}
uniform sampler2D A; uniform sampler2D B;
uniform vec4 taps[${2 * MAX_TAPS}];
uniform int n;
uniform vec2 cA; uniform vec2 cB;     // the transforms' centres, logical px
uniform vec3 ink;
uniform vec2 dir;                     // wipe: the edge's unit direction
uniform vec2 track;                   // wipe: the edge's run along dir; iris: its radius, both from progress 0 to 1
uniform float soft;                   // wipe, iris: the edge's width, logical px
uniform vec2 center;                  // iris: the circle's centre
uniform vec3 edgeLight;               // wipe, iris: the edge line's light (glow level; 0 for none)
uniform vec2 edgeNow;                 // wipe, iris: the edge's progress and light at the frame's own time (mid-shutter)
uniform vec3 flashLight;              // flash: the flash's light
uniform float seed; uniform float amount; // glitch
const vec2 FR = vec2(${W}.0, ${H}.0);

vec3 fetch(sampler2D t, vec2 q) { return texture(t, vec2(q.x / FR.x, 1.0 - q.y / FR.y)).rgb; }
float inside(vec2 q) { return (q.x >= 0.0 && q.x <= FR.x && q.y >= 0.0 && q.y <= FR.y) ? 1.0 : 0.0; }
// a placement's source point for screen point p: c + R(−r)·(p − t − c) / s
vec2 place(vec2 p, vec4 x, vec2 c) {
  vec2 d = (p - x.xy - c) / x.z;
  if (x.w != 0.0) d = rot2(x.w) * d;
  return c + d;
}
// the frame reflected at its edges (a spin never shows ink in its corners)
vec2 mirror(vec2 q) { return FR - abs(mod(q, 2.0 * FR) - FR); }

vec3 gA, gB; // wipe, iris, flash: the pictures do not move, so they are read once per pixel

vec3 shade(vec2 p, vec4 s0, vec4 s1, vec4 s2) {
#if defined(KIND_WIPE) || defined(KIND_IRIS)
#ifdef KIND_WIPE
  float d = dot(p, dir);
#else
  float d = length(p - center);
#endif
  float e = mix(track.x, track.y, s2.y);
  vec3 c = mix(gA, gB, 1.0 - smoothstep(e - 0.5 * soft, e + 0.5 * soft, d));
  // the edge's faint spill either side, as light, streaked over the shutter (its crisp core is drawn once, in main)
  if (s2.z > 0.0) c += edgeLight * s2.z * 0.05 * exp(-abs(d - e) / (0.3 * soft + 1.0));
  return c;
#elif defined(KIND_SLIDE)
  vec2 qa = place(p, s0, cA), qb = place(p, s1, cB);
  // A recedes as a card: its corners round as it shrinks (1 px of anti-aliasing on screen)
  float rr = 0.04 * min(FR.x, FR.y) * s2.y / 0.6;
  float sd = sdBox(qa - 0.5 * FR, 0.5 * FR - rr) - rr;
  float cov = sat(0.5 - sd * s0.z);
  vec3 a = mix(ink, fetch(A, qa), cov);
  a = mix(a, ink, s2.y);
  // the shadow B's leading edge casts on A
  vec2 o = max(s1.xy - p, p - s1.xy - FR);
  a = mix(a, ink, s2.z * exp(-length(max(o, 0.0)) / (0.06 * min(FR.x, FR.y))));
  return inside(qb) > 0.0 ? fetch(B, qb) : a;
#elif defined(KIND_SPIN)
  vec3 a = fetch(A, mirror(place(p, s0, cA))), b = fetch(B, mirror(place(p, s1, cB)));
  return mix(a, b, s2.x);
#elif defined(KIND_FLASH)
  float f = s2.y;
  vec3 c = mix(gA, gB, s2.x) * (1.0 + 4.0 * f * f);
  return mix(c, flashLight, smoothstep(0.15, 1.0, f));
#elif defined(KIND_GLITCH)
  float g = s2.y, st = s2.z, s7 = seed * 97.0;
  // rows of a height picked per frame; a share of them, growing with g, tear sideways, and some show the other picture
  float rows = floor(mix(12.0, 44.0, hash11(st * 1.37 + s7)));
  float row = floor(p.y / (FR.y / rows));
  float h1 = hash12(vec2(row, st) + s7), h2 = hash12(vec2(row * 1.7 + 3.1, st) + s7 * 0.5), h3 = hash12(vec2(row * 0.31 + 7.7, st * 1.3) + s7 * 0.25);
  float on = step(1.0 - 0.55 * g, h1);
  float dx = on * (h2 - 0.5) * 0.28 * FR.x * g * amount;
  // blocks: a few cells of the frame jump by a cell-sized step
  float bs = min(FR.x, FR.y) / floor(mix(6.0, 14.0, hash11(st * 0.71 + s7 * 3.0)));
  vec2 cell = floor(p / bs);
  float hb = hash12(cell * 1.31 + vec2(st, s7));
  vec2 jump = hb < 0.12 * g ? (hash22(cell + st + s7) - 0.5) * 2.0 * bs * amount : vec2(0.0);
  vec2 q = vec2(mod(p.x - dx + jump.x, FR.x), clamp(p.y + jump.y, 0.0, FR.y));
  float split = (0.004 + 0.016 * on) * FR.x * g * amount;
  bool useB = (s2.x > 0.5) != (on > 0.5 && h3 < 0.45 * g);
  vec2 qr = vec2(mod(q.x + split, FR.x), q.y), qbl = vec2(mod(q.x - split, FR.x), q.y);
  return useB ? vec3(fetch(B, qr).r, fetch(B, q).g, fetch(B, qbl).b) : vec3(fetch(A, qr).r, fetch(A, q).g, fetch(A, qbl).b);
#else
  return ink;
#endif
}

void main() {
  vec2 p = vec2(vUv.x, 1.0 - vUv.y) * FR;
#if defined(KIND_WIPE) || defined(KIND_IRIS) || defined(KIND_FLASH)
  gA = fetch(A, p); gB = fetch(B, p);
#endif
  vec3 sum = vec3(0.0);
  if (n <= 1) sum = shade(p, taps[0], taps[1], taps[2]);
  else {
    for (int k = 0; k < ${MAX_FX_TAPS - 1}; k++) {
      if (k >= n - 1) break;
      int i = 3 * k;
      vec4 a0 = taps[i], a1 = taps[i + 1], a2 = taps[i + 2], b0 = taps[i + 3], b1 = taps[i + 4], b2 = taps[i + 5];
      for (int j = 0; j < ${SUB_TAPS}; j++) {
        float f = (float(j) + 0.5) / ${SUB_TAPS}.0;
        sum += shade(p, mix(a0, b0, f), mix(a1, b1, f), mix(a2, b2, f));
      }
    }
    sum /= float((n - 1) * ${SUB_TAPS});
  }
#if defined(KIND_WIPE) || defined(KIND_IRIS)
  // the edge line's core: a crisp 2 px line where the edge is at the frame's own time. Streaked over the shutter like
  // the rest, a fast edge's thin line smears into a dim bar a couple of hundred px wide; a light that leads the reveal
  // reads as one, sharp, with its spill trailing.
  if (edgeNow.y > 0.0) {
#ifdef KIND_WIPE
    float x = dot(p, dir) - mix(track.x, track.y, edgeNow.x);
#else
    float x = length(p - center) - mix(track.x, track.y, edgeNow.x);
#endif
    sum += edgeLight * edgeNow.y * exp(-x * x / 2.0);
  }
#endif
  fragColor = vec4(sum, 1.0);
}`;

/** The P and Q slots of an effects kind's third vec4 (see fxFrag). */
function fxSlots(kind: TransitionKind, s: TransitionState): [number, number] {
  switch (kind) {
    case 'wipe': case 'iris': return [s.edge ?? 0, s.light ?? 0];
    case 'slide': return [s.dim ?? 0, s.shadow ?? 0];
    case 'flash': return [s.light ?? 0, 0];
    case 'glitch': return [s.glitch ?? 0, s.step ?? 0];
    default: return [0, 0];
  }
}

/** A colour's light with its brightest channel at `level` (hue kept). */
const atLevel = (c: [number, number, number], level: number): [number, number, number] => {
  const m = Math.max(c[0], c[1], c[2], 1e-6);
  return [(c[0] * level) / m, (c[1] * level) / m, (c[2] * level) / m];
};
/** A flash peaks just past display white: neutral light whitens without blooming, an accent's blooms a little. */
const FLASH_LEVEL = 1.25;

/**
 * Draws a transition: A and B (the two scenes' HDR outputs) through `taps` (the frame's shutterTaps, at most MAX_TAPS,
 * MAX_FX_TAPS for an effects kind) into `out` (HDR linear, a target of its own: it never reads what it writes). With
 * more than one tap it samples SUB_TAPS points along each span between adjacent taps, their states interpolated, and
 * averages them all: the transition's motion blurred over the shutter. The original kinds draw with the original
 * program, untouched; the effects kinds (`o.entry` an effects kind) with theirs.
 */
export class TransitionPass {
  private pass: FSPass;
  private fx = new Map<TransitionKind, FSPass>();
  private buf = new Float32Array(2 * MAX_TAPS * 4);

  constructor() {
    this.pass = new FSPass(frag(), {
      A: { value: null }, B: { value: null }, taps: { value: this.buf }, n: { value: 1 }, isMatch: { value: false },
      cA: { value: new THREE.Vector2(W / 2, H / 2) }, cB: { value: new THREE.Vector2(W / 2, H / 2) }, soft: { value: 0.12 },
      ink: { value: new THREE.Vector3(...LIN.bg) },
    });
  }

  /** `o.soft`: match's luma-key softness (the spec's `soft`, default 0.12); `o.entry`: the transition (effects kinds). */
  render(r: THREE.WebGLRenderer, a: THREE.Texture, b: THREE.Texture, taps: TransitionState[], out: THREE.WebGLRenderTarget, o: { soft?: number; entry?: TransitionEntry } = {}): void {
    if (o.entry && isFxKind(o.entry.spec.kind)) return this.renderFx(r, a, b, taps, out, o.entry);
    if (taps.length < 1 || taps.length > MAX_TAPS) throw new Error(`TransitionPass takes 1 to ${MAX_TAPS} taps, got ${taps.length}`);
    const u = this.pass.u, isMatch = taps[0]!.match > -1;
    taps.forEach((s, k) => {
      this.buf.set([s.a.tx, s.a.ty, s.a.s, s.wB, s.b.tx, s.b.ty, s.b.s, isMatch ? s.match : s.ink], 8 * k);
    });
    u.A!.value = a;
    u.B!.value = b;
    u.n!.value = taps.length;
    u.isMatch!.value = isMatch;
    (u.cA!.value as THREE.Vector2).set(taps[0]!.a.cx, taps[0]!.a.cy);
    (u.cB!.value as THREE.Vector2).set(taps[0]!.b.cx, taps[0]!.b.cy);
    u.soft!.value = o.soft ?? 0.12;
    this.pass.render(r, out);
  }

  private renderFx(r: THREE.WebGLRenderer, a: THREE.Texture, b: THREE.Texture, taps: TransitionState[], out: THREE.WebGLRenderTarget, e: TransitionEntry): void {
    const kind = e.spec.kind;
    if (taps.length < 1 || taps.length > MAX_FX_TAPS) throw new Error(`TransitionPass takes 1 to ${MAX_FX_TAPS} taps for a ${kind}, got ${taps.length}`);
    let pass = this.fx.get(kind);
    if (!pass) {
      pass = new FSPass(fxFrag(kind), {
        A: { value: null }, B: { value: null }, taps: { value: this.buf }, n: { value: 1 },
        cA: { value: new THREE.Vector2(W / 2, H / 2) }, cB: { value: new THREE.Vector2(W / 2, H / 2) },
        ink: { value: new THREE.Vector3(...LIN.bg) }, dir: { value: new THREE.Vector2(1, 0) }, track: { value: new THREE.Vector2(0, 1) },
        soft: { value: 1 }, center: { value: new THREE.Vector2(W / 2, H / 2) }, edgeLight: { value: new THREE.Vector3() },
        flashLight: { value: new THREE.Vector3() }, seed: { value: 0 }, amount: { value: 1 }, edgeNow: { value: new THREE.Vector2() },
      });
      this.fx.set(kind, pass);
    }
    taps.forEach((s, k) => {
      const [P, Q] = fxSlots(kind, s);
      this.buf.set([s.a.tx, s.a.ty, s.a.s, s.a.r ?? 0, s.b.tx, s.b.ty, s.b.s, s.b.r ?? 0, s.wB, P, Q, 0], 12 * k);
    });
    const u = pass.u, sp = e.spec;
    u.A!.value = a;
    u.B!.value = b;
    u.n!.value = taps.length;
    (u.cA!.value as THREE.Vector2).set(taps[0]!.a.cx, taps[0]!.a.cy);
    (u.cB!.value as THREE.Vector2).set(taps[0]!.b.cx, taps[0]!.b.cy);
    if (kind === 'wipe') {
      const w = wipeTrack(sp);
      (u.dir!.value as THREE.Vector2).set(...w.dir);
      (u.track!.value as THREE.Vector2).set(w.d0, w.d1);
      u.soft!.value = w.soft;
    } else if (kind === 'iris') {
      const w = irisTrack(sp);
      (u.center!.value as THREE.Vector2).set(...w.center);
      (u.track!.value as THREE.Vector2).set(w.r0, w.r1);
      u.soft!.value = w.soft;
    }
    (u.edgeLight!.value as THREE.Vector3).set(...(sp.edge ? glow(sp.edge) : ([0, 0, 0] as [number, number, number])));
    // the frame's own state: the middle tap (the taps are centred on the frame's time), or the middle two's mean
    const m0 = taps[(taps.length - 1) >> 1]!, m1 = taps[taps.length >> 1]!;
    (u.edgeNow!.value as THREE.Vector2).set(((m0.edge ?? 0) + (m1.edge ?? 0)) / 2, ((m0.light ?? 0) + (m1.light ?? 0)) / 2);
    (u.flashLight!.value as THREE.Vector3).set(...atLevel(lin(sp.color ?? 'fg'), FLASH_LEVEL));
    u.seed!.value = pairSeed(e.id);
    u.amount!.value = sp.amount ?? 1;
    pass.render(r, out);
  }

  dispose(): void {
    this.pass.mat.dispose();
    for (const p of this.fx.values()) p.mat.dispose();
    this.fx.clear();
  }
}
