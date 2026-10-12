// Warp: a starfield rushing past, stars stretching into streaks as it speeds up. With `pulse`, every beat (or downbeat)
// kicks the speed up and lets it ease back, the streaks lengthening with it: the ramp is integrated exactly from the
// beat grid (warpTravel), so any frame renders the same in any order. Most streaks are the dim fg (it never blooms); a
// share run in the inks, the nearest heads hot enough to bloom. A soft tunnel haze glows at the vanishing point.
//
// Params (and every background param, base.ts; pulse drives the ramp):
//   boost 3           how much a beat kicks the speed (times the base speed)
//   streak 1          streak length (times)
//   density 1         stars (times)
//   center [0.5, 0.5] the vanishing point (fractions of the frame, y down)
//   inked 0.45        the share of streaks in the inks (the rest in fgDim)
//   haze 0.5          the tunnel's glow at the vanishing point
import * as THREE from 'three';
import { BgScene, pulseAt, type Pulse } from './base';
import type { Frame } from '../../engine/scene';

/**
 * The area under the house pulse (1 on each beat, halving every `hl` beats, cut off by the next beat: motion.ts onBeat)
 * from beat 0 to beat `beat`, in beats. Continuous, and exact for any beat, so a speed ramp driven by it is a pure
 * function of time. `period` is the beats between pulses (1 for every beat; beatsPerBar for downbeats).
 */
export function pulseArea(beat: number, hl: number, period = 1): number {
  const C = hl / Math.LN2, n = Math.floor(beat / period), ph = beat - n * period;
  return n * C * (1 - Math.pow(0.5, period / hl)) + C * (1 - Math.pow(0.5, ph / hl));
}

/** How far the field has travelled at a frame (base units: seconds at speed 1), and its speed now. */
export function warpTravel(o: { time: number; speed: number; boost: number; pulse: Pulse; beat: number; beatsPerBar: number; secondsPerBeat: number; now: number }): { travel: number; vel: number } {
  if (o.pulse === 'none' || o.boost === 0) return { travel: o.time, vel: o.speed };
  const [hl, period] = o.pulse === 'beat' ? [0.3, 1] : [0.6, o.beatsPerBar || 4];
  return { travel: o.time + o.boost * o.speed * o.secondsPerBeat * pulseArea(o.beat, hl, period), vel: o.speed * (1 + o.boost * o.now) };
}

export class Warp extends BgScene {
  private own = {
    uTravel: { value: 0 }, uVel: { value: 1 }, uStreak: { value: 1 }, uDensity: { value: 1 },
    uCenter: { value: new THREE.Vector2(0.5, 0.5) }, uInked: { value: 0.45 }, uHaze: { value: 0.5 },
  };

  protected override uniforms() {
    return this.own;
  }

  protected override update(f: Frame, time: number) {
    const o = this.own, a = this.ctx.audio, b = Math.floor(f.beat);
    const pulse = this.k<Pulse>('pulse', 'none');
    const spb = a.timeOfBeat(b + 1) - a.timeOfBeat(b);
    const w = warpTravel({ time, speed: this.k('speed', 1), boost: this.k('boost', 3), pulse, beat: f.beat, beatsPerBar: f.beatsPerBar, secondsPerBeat: spb, now: pulseAt(pulse, f) });
    o.uTravel.value = w.travel;
    o.uVel.value = w.vel;
    o.uStreak.value = this.k('streak', 1);
    o.uDensity.value = Math.max(0.1, this.k('density', 1));
    const c = this.k<[number, number]>('center', [0.5, 0.5]);
    o.uCenter.value.set(c[0], 1 - c[1]);
    o.uInked.value = this.k('inked', 0.45);
    o.uHaze.value = this.k('haze', 0.5);
  }

  protected effect() {
    return /* glsl */ `
uniform float uTravel, uVel, uStreak, uDensity, uInked, uHaze; uniform vec2 uCenter;

vec4 effect(vec2 p0, vec2 uv) {
  float S = min(uRes.x, uRes.y);
  vec2 p = (uv - uCenter) * uRes / S / uScale;
  float r = length(p), a = atan(p.y, p.x) / TAU + 0.5;
  float px = 1.0 / S / uScale;
  vec3 acc = vec3(0.0);
  float cover = 0.0;
  for (int l = 0; l < 3; l++) {
    float fl = float(l);
    float N = floor((110.0 + 70.0 * fl) * uDensity);
    float k0 = floor(a * N + fl * 0.37);
    for (int j = -1; j <= 1; j++) {
      float k = k0 + float(j);
      float kk = mod(k, N);
      vec2 h = hash22(vec2(kk, fl * 13.1 + uSeed * 7.0));
      float h3 = hash12(vec2(kk * 1.7, fl + uSeed * 3.0));
      float as = (k + 0.25 + 0.5 * h.x - fl * 0.37) / N;  // the star's angle (turns)
      float v = mix(0.12, 0.3, h.y);                        // its speed through depth
      float z = 1.0 - fract(h3 + uTravel * v);               // depth: 1 far .. 0 here
      float zt = z + v * uVel * 0.16 * uStreak;              // where it was a moment ago: the streak's tail
      float R0 = mix(0.02, 0.05, h.x);
      float rh = R0 / max(z, 0.02), rt = R0 / zt;
      // distance across the streak (arc length) and along it
      float da = (a - as) - floor(a - as + 0.5);
      float across = abs(da) * TAU * r;
      float wdt = px * mix(0.6, 2.2, sat(1.0 - z)) ;
      float along = smoothstep(rt - px, rt + px, r) * (1.0 - smoothstep(rh - px, rh + px * 2.0, r));
      // brighter toward the head
      float headK = sat((r - rt) / max(rh - rt, 1e-4));
      float line = sat((wdt + px * 0.75 - across) / (1.5 * px)) * along;
      float energy = wdt / max(wdt, px * 1.2);
      float near = pow(smoothstep(0.92, 0.25, z), 1.5);
      float b = line * near * energy * mix(0.35, 1.0, headK * headK);
      float inked = step(h.y, uInked);
      vec3 col = inked > 0.5 ? (h.x < 0.6 ? ink1(near * headK * 0.9) : ink2(near * headK * 0.7)) : C_FG_DIM * 0.8;
      acc += col * b;
      cover += b * 0.4;
    }
  }
  // the tunnel's haze at the vanishing point, swelling with the speed
  float speedK = sat((uVel - 1.0) * 0.25);
  acc += uColor2 * uHaze * 0.12 * exp(-r / 0.18) * (1.0 + speedK);
  acc += uColor * uHaze * 0.05 * exp(-r / 0.5);
  return vec4(acc * uIntensity, sat(cover));
}`;
  }
}

export default Warp;
