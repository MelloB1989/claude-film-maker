// Particles: dust in a lit room, in depth. Layers of motes drift and rise at their depth's parallax; the layer at the
// focal plane is sharp points (a few run hot in the first ink and bloom), the ones before and behind it open into soft
// bokeh discs with a faint rim, dimmer as they spread. Pure function of time: each mote's place is its cell's hash and
// the clock, so nothing accumulates.
//
// Params (and every background param, base.ts):
//   layers 5          depth layers (1..7), far to near
//   density 1         motes per layer (times)
//   focus 0.45        the depth in focus: 0 the far layer, 1 the near one
//   bokeh 1           how wide out-of-focus motes open (0: everything sharp)
//   drift [0.15, 0.6] how they move (per second, times speed): sideways and upward
//   mix 0.35          how many motes take the second ink (0..1)
import * as THREE from 'three';
import { BgScene } from './base';
import type { Frame } from '../../engine/scene';

export class Particles extends BgScene {
  private own = {
    uLayers: { value: 5 }, uDensity: { value: 1 }, uFocus: { value: 0.45 }, uBokeh: { value: 1 },
    uDrift: { value: new THREE.Vector2(0.15, 0.6) }, uMix: { value: 0.35 },
  };

  protected override uniforms() {
    return this.own;
  }

  protected override update(_f: Frame) {
    const o = this.own;
    o.uLayers.value = Math.max(1, Math.min(7, Math.round(this.k('layers', 5))));
    o.uDensity.value = Math.max(0.1, this.k('density', 1));
    o.uFocus.value = this.k('focus', 0.45);
    o.uBokeh.value = Math.max(0, this.k('bokeh', 1));
    const d = this.k<[number, number]>('drift', [0.15, 0.6]);
    o.uDrift.value.set(d[0], d[1]);
    o.uMix.value = this.k('mix', 0.35);
  }

  protected effect() {
    return /* glsl */ `
uniform int uLayers; uniform float uDensity, uFocus, uBokeh, uMix; uniform vec2 uDrift;

vec4 effect(vec2 p, vec2 uv) {
  float t = uTime;
  vec3 acc = vec3(0.0);
  float cover = 0.0;
  float px = 1.0 / min(uRes.x, uRes.y); // one logical px, in p units
  for (int l = 0; l < 7; l++) {
    if (l >= uLayers) break;
    float depth = uLayers > 1 ? float(l) / float(uLayers - 1) : 0.5; // 0 far .. 1 near
    float persp = mix(0.45, 1.6, depth);                              // parallax and size with nearness
    float cells = mix(16.0, 5.0, depth) * sqrt(uDensity) / uScale;   // motes per short side
    float coc = abs(depth - uFocus) * uBokeh;                         // circle of confusion
    vec2 off = uDrift * t * persp * 0.08 * vec2(1.0, 1.0) + vec2(float(l) * 7.31 + uSeed * 3.1, float(l) * 3.77);
    // a slow sway along the drift
    off.x += 0.03 * persp * sin(t * 0.3 + float(l) * 1.7);
    vec2 g = (p - off) * cells;
    vec2 id0 = floor(g);
    for (int j = -1; j <= 1; j++) for (int i = -1; i <= 1; i++) {
      vec2 id = id0 + vec2(i, j);
      vec2 h = hash22(id + float(l) * 31.7 + uSeed * 17.0);
      float alive = step(mix(0.45, 0.8, depth), hash12(id * 1.31 + float(l) * 5.1 + uSeed));
      vec2 c = id + 0.15 + 0.7 * h;
      float r0 = mix(1.2, 3.2, hash12(id + 7.7)) * persp * px * cells;     // the mote's own radius (grid units)
      float r = r0 + coc * mix(0.06, 0.2, hash12(id + 2.2));                 // opened by defocus
      float d = length(g - c);
      float aa = 0.75 * px * cells; // (analytic: no derivatives inside the loop)
      float disc = 1.0 - smoothstep(r - aa - 0.6 * sat(coc * 4.0) * r, r + aa, d);
      // energy spreads with the disc: a defocused mote is dimmer, with a faint brighter rim
      float energy = r0 * r0 / (r * r);
      float rim = 1.0 + 0.9 * smoothstep(r * 0.4, r * 0.85, d) * sat(coc * 6.0);
      float tw = 0.65 + 0.35 * sin(t * (0.8 + 1.7 * h.x) + h.y * 6.28);
      float b = alive * disc * rim * tw * mix(0.1, 1.0, sqrt(energy)) * mix(0.45, 1.0, depth);
      // a few sharp motes near the focal plane run hot
      float hotK = step(0.86, hash12(id + 4.4)) * (1.0 - sat(coc * 5.0));
      vec3 col = hash12(id + 9.9) < uMix ? ink2(hotK * 0.6) : ink1(hotK);
      // dust is mostly pale: the inks tint it, and only the hot motes are pure ink
      col = mix(mixD(C_FG_DIM * 0.7, col, 0.55), col, hotK);
      acc += col * b * 0.55 * (1.0 + 1.2 * uPulse * hotK + 0.4 * uPulse);
      cover += alive * disc * 0.25 * energy;
    }
  }
  return vec4(acc * uIntensity, sat(cover));
}`;
  }
}

export default Particles;
