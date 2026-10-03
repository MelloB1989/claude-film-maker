// The transition's compositing pass: two scenes' HDR frames (A and B) into one, through the transition's states over the
// shutter (transition.ts shutterTaps). One full-screen pass: per sample it places A and B by their transforms, shows ink
// where neither covers the pixel, weighs them (wB, or match's luma key on A's display value), dips toward ink, and
// averages. Every output is a convex mix of A, B and ink, so it never brightens anything: bone stays under the bloom.
import * as THREE from 'three';
import { FSPass, W, H } from './gl';
import { LIN } from './palette';
import { SHOULDER_GLSL } from './post';
import { MAX_TAPS, SUB_TAPS, type TransitionState } from './transition';

const FRAG = /* glsl */ `
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
  fragColor = vec4(sum, 1.0);
}`;

/**
 * Draws a transition: A and B (the two scenes' HDR outputs) through `taps` (the frame's shutterTaps, at most MAX_TAPS)
 * into `out` (HDR linear, a target of its own: it never reads what it writes). With more than one tap it samples
 * SUB_TAPS points along each span between adjacent taps, their states interpolated, and averages them all: the
 * transition's motion blurred over the shutter.
 */
export class TransitionPass {
  private pass: FSPass;
  private buf = new Float32Array(2 * MAX_TAPS * 4);

  constructor() {
    this.pass = new FSPass(FRAG, {
      A: { value: null }, B: { value: null }, taps: { value: this.buf }, n: { value: 1 }, isMatch: { value: false },
      cA: { value: new THREE.Vector2(W / 2, H / 2) }, cB: { value: new THREE.Vector2(W / 2, H / 2) }, soft: { value: 0.12 },
      ink: { value: new THREE.Vector3(...LIN.ink) },
    });
  }

  /** `o.soft`: match's luma-key softness (the spec's `soft`, default 0.12). */
  render(r: THREE.WebGLRenderer, a: THREE.Texture, b: THREE.Texture, taps: TransitionState[], out: THREE.WebGLRenderTarget, o: { soft?: number } = {}): void {
    if (taps.length < 1 || taps.length > MAX_TAPS) throw new Error(`TransitionPass takes 1 to ${MAX_TAPS} taps, got ${taps.length}`);
    const u = this.pass.u, isMatch = taps[0]!.match >= 0;
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

  dispose(): void {
    this.pass.mat.dispose();
  }
}
