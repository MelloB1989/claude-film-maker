// Aurora: curtains of light drifting across a dark sky. A few ribbons, each a hanging curtain with a bright lower hem
// (its core runs hot in the first ink and blooms), fine vertical rays that slide along it, and a long soft tail fading
// up into the second ink. Quiet enough that type reads over it at the default intensity.
//
// Params (and every background param, base.ts: color, color2, background, intensity, speed, scale, seed, pulse, glow,
// clock, offset):
//   ribbons 3        how many curtains (1..5)
//   height 0.5       where they hang: 0 the bottom of the frame, 1 the top
//   spread 0.3       how far apart they hang (fractions of the frame's height)
//   rays 1           how strongly the vertical rays read (0: smooth curtains)
//   stars 0.4        a faint star field behind (0: none)
import { BgScene } from './base';
import type { Frame } from '../../engine/scene';

export class Aurora extends BgScene {
  private own = { uRibbons: { value: 3 }, uHeight: { value: 0.5 }, uSpread: { value: 0.3 }, uRays: { value: 1 }, uStars: { value: 0.4 } };

  protected override uniforms() {
    return this.own;
  }

  protected override update(_f: Frame) {
    this.own.uRibbons.value = Math.max(1, Math.min(5, Math.round(this.k('ribbons', 3))));
    this.own.uHeight.value = this.k('height', 0.5);
    this.own.uSpread.value = this.k('spread', 0.3);
    this.own.uRays.value = this.k('rays', 1);
    this.own.uStars.value = this.k('stars', 0.4);
  }

  protected effect() {
    return /* glsl */ `
uniform int uRibbons; uniform float uHeight, uSpread, uRays, uStars;

vec4 effect(vec2 p, vec2 uv) {
  float t = uTime;
  float aspect = uRes.x / uRes.y;
  // the frame in units of its height: curtains span it whatever the format
  vec2 q = vec2((uv.x - 0.5) * aspect, uv.y) / uScale;
  vec3 acc = vec3(0.0);
  float cover = 0.0;
  for (int i = 0; i < 5; i++) {
    if (i >= uRibbons) break;
    float fi = float(i), n = max(float(uRibbons) - 1.0, 1.0);
    float s = uSeed * 7.31 + fi * 17.13;
    // the hem: a slow wandering line, higher for the back curtains
    float y0 = (uHeight + (fi / n - 0.5) * uSpread * (uRibbons > 1 ? 1.0 : 0.0)) / uScale;
    float x = q.x + 0.06 * sin(t * 0.05 + s);
    float hem = y0 + 0.16 * fbm(vec2(x * 0.45 + s, t * 0.04 + s * 0.3), 3) + 0.06 * sin(x * 1.6 + t * 0.11 + s);
    float d = q.y - hem;
    // the curtain folds: x displaced along the hem, so rays lean with it
    float fold = x + 0.25 * fbm(vec2(x * 1.3 - t * 0.03, s), 2);
    float rays = snoise(vec2(fold * 14.0 + s, t * 0.09 + s)) * 0.5 + 0.5;
    rays = mix(1.0, 0.35 + 0.9 * rays * rays, sat(uRays));
    float fine = snoise(vec2(fold * 46.0 - s, t * 0.2)) * 0.5 + 0.5;
    rays *= mix(1.0, 0.7 + 0.5 * fine, 0.5 * sat(uRays));
    // a sharp lower hem, a long tail upward whose length breathes along the curtain
    float tail = 0.07 + 0.12 * pow(snoise(vec2(fold * 1.7 + s, t * 0.06)) * 0.5 + 0.5, 2.0);
    float below = exp(-pow(max(-d, 0.0) / 0.028, 2.0));
    float above = exp(-max(d, 0.0) / tail) * smoothstep(-0.06, 0.0, d);
    float body = d < 0.0 ? below : above;
    // brightness varies along the curtain: patches come and go
    float patchK = smoothstep(-0.2, 0.75, snoise(vec2(x * 0.75 + s * 0.5, t * 0.05 - s)));
    float w = body * rays * (0.08 + 0.92 * patchK);
    float rim = exp(-abs(d) / 0.01) * (0.1 + 0.9 * patchK) * rays;
    float front = 1.0 - 0.35 * fi / n; // the back curtains are fainter
    // the hem in the first ink, rising into the second
    float up = smoothstep(-0.02, tail * 1.4, d);
    vec3 col = mixD(uColor, uColor2, sat(up + 0.25 * sin(fi * 2.3 + x * 0.8 + t * 0.04)));
    acc += front * (col * w * 0.2 + ink1(0.55 + 0.45 * uPulse) * rim * 0.13);
    cover += front * w * 0.1;
  }
  acc *= uIntensity * (1.0 + uPulse);
  // a low sky glow under the curtains, and faint stars above
  acc += uColor * 0.008 * uIntensity * smoothstep(0.9, 0.0, uv.y);
  vec2 sp = floor(p * 260.0 + uSeed * 31.0);
  float star = step(0.9965, hash12(sp));
  vec2 so = fract(p * 260.0 + uSeed * 31.0) - 0.5;
  float tw = 0.6 + 0.4 * sin(t * (1.0 + 2.0 * hash12(sp + 3.0)) + hash12(sp + 9.0) * 6.28);
  acc += C_FG_DIM * 0.3 * uStars * star * tw * smoothstep(0.32, 0.08, length(so)) * smoothstep(0.25, 0.9, uv.y) * (1.0 - sat(cover * 4.0));
  return vec4(acc, sat(cover));
}`;
  }
}

export default Aurora;
