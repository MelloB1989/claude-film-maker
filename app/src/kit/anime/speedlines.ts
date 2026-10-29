// SpeedLines: the manga's speed lines, redrawn on twos like hand animation. 'focus' (集中線) rings the frame with
// wedges converging on a point, an empty eye around it; 'parallel' streaks the frame along an angle (a dash, a fall).
// Transparent by default: stack it over the action.
//
// Params (and BgScene's: color '#f4f1ea', intensity 1, seed):
//   mode 'focus'      'focus' or 'parallel'
//   center [0.5, 0.5] focus: the point the lines converge on (uv, from the bottom left)
//   inner 0.3         focus: the empty eye's radius (short sides)
//   count 110         lines around the circle (focus) or across the frame (parallel)
//   angle 0           parallel: the streaks' direction, degrees
//   thickness 1       how heavy the lines are
//   step 12           redraws a second (12: on twos at 24 fps)
import * as THREE from 'three';
import { BgScene } from '../bg/base';

export class SpeedLines extends BgScene {
  protected override defaults = { background: 'none', color: '#f4f1ea', speed: 1 } as Record<string, unknown>;
  private u = {
    uCenter: { value: new THREE.Vector2(0.5, 0.5) }, uInner: { value: 0.3 }, uCount: { value: 110 }, uStep: { value: 12 },
    uThick: { value: 1 }, uMode: { value: 0 }, uAngle: { value: 0 },
  };

  protected override uniforms() {
    return this.u;
  }

  protected effect() {
    return /* glsl */ `
uniform vec2 uCenter; uniform float uInner, uCount, uStep, uThick, uMode, uAngle;
vec4 effect(vec2 p, vec2 uv) {
  vec2 asp = uRes / min(uRes.x, uRes.y);
  float px = 1.0 / min(uRes.x, uRes.y);
  float st = floor(uTime * uStep);
  float m = 0.0;
  if (uMode < 0.5) {
    vec2 d = p - (uCenter - 0.5) * asp;
    float r = length(d);
    float k = (atan(d.y, d.x) / 6.2831853 + 0.5) * uCount;
    float id = floor(k);
    float h = hash12(vec2(id, st) + uSeed), h2 = hash12(vec2(id * 1.31, st + 7.0) + uSeed);
    float start = uInner * (0.75 + 0.75 * h2);
    float w = (0.06 + 0.4 * h * h) * sat((r - start) / 0.5) * uThick;   // a wedge that widens outward
    float cellPx = 6.2831853 * r / uCount / px;                          // a cell's width in px at this radius
    float aa = 1.0 / max(cellPx, 1.0);
    m = smoothstep(w + aa, w - aa, abs(fract(k) - 0.5)) * step(0.22, h);
  } else {
    vec2 q = rot2(-uAngle) * p;
    float k = q.y * uCount * 0.5;
    float id = floor(k);
    float h = hash12(vec2(id, st) + uSeed);
    float len = 0.25 + 0.9 * hash12(vec2(id, st + 3.0) + uSeed);
    float x0 = (hash12(vec2(id, st + 5.0) + uSeed) - 0.5) * 3.2;
    float along = smoothstep(x0 - len, x0 - 0.6 * len, q.x) * (1.0 - smoothstep(x0 - 0.02, x0, q.x));
    float w = (0.04 + 0.22 * h * h) * uThick;
    float aa = 1.0 / max(2.0 / (uCount * px), 1.0);
    m = smoothstep(w + aa, w - aa, abs(fract(k) - 0.5)) * along * step(0.35, h);
  }
  m = sat(m * uIntensity);
  return vec4(uColor * m, m);
}`;
  }

  protected override update() {
    const c = this.k<[number, number]>('center', [0.5, 0.5]);
    this.u.uCenter.value.set(c[0], c[1]);
    this.u.uInner.value = this.k('inner', 0.3);
    this.u.uCount.value = this.k('count', 110);
    this.u.uStep.value = this.k('step', 12);
    this.u.uThick.value = this.k('thickness', 1);
    this.u.uMode.value = this.k<string>('mode', 'focus') === 'parallel' ? 1 : 0;
    this.u.uAngle.value = (this.k('angle', 0) * Math.PI) / 180;
  }
}

export default SpeedLines;
