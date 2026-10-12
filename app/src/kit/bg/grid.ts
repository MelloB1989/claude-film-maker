// Grid: a floor of hairlines receding to a glowing horizon and scrolling toward the viewer, or a flat field of dots or
// lines under a drifting pool of light. Lines are a constant hairline width on screen at any distance and fade into the
// haze before they could alias (no moiré); the horizon's line runs hot in the first ink and blooms.
//
// Params (and every background param, base.ts):
//   mode 'floor'      'floor' (perspective) | 'dots' | 'lines' (flat)
//   cell 1            the grid's spacing (times scale): 'floor' world units, flat in 1/12ths of the short side
//   line 1.4          the hairline's width in px (logical)
//   horizon 0.42      'floor': where the horizon sits, 0 the bottom of the frame, 1 the top
//   tilt 0            'floor': a slow roll of the camera, in degrees
//   drift [0, 1]      how the grid scrolls (per second, times speed): 'floor' sideways and toward the viewer
//   light 0.8         flat: how strongly a drifting pool of light lifts the marks under it into the first ink
import { BgScene } from './base';
import type { Frame } from '../../engine/scene';
import * as THREE from 'three';

export class Grid extends BgScene {
  private own = {
    uMode: { value: 0 }, uCell: { value: 1 }, uLine: { value: 1.4 }, uHorizon: { value: 0.42 }, uTilt: { value: 0 },
    uDrift: { value: new THREE.Vector2(0, 1) }, uLight: { value: 0.5 },
  };

  protected override uniforms() {
    return this.own;
  }

  override init() {
    const mode = this.k('mode', 'floor');
    if (!['floor', 'dots', 'lines'].includes(mode)) throw new Error(`shot ${this.ctx.id}: Grid mode is 'floor', 'dots' or 'lines', got '${mode}'`);
    super.init();
  }

  protected override update(_f: Frame) {
    const o = this.own;
    o.uMode.value = ['floor', 'dots', 'lines'].indexOf(this.k('mode', 'floor'));
    o.uCell.value = Math.max(0.05, this.k('cell', 1));
    o.uLine.value = Math.max(0.5, this.k('line', 1.4));
    o.uHorizon.value = this.k('horizon', 0.42);
    o.uTilt.value = (this.k('tilt', 0) * Math.PI) / 180;
    const d = this.k<[number, number]>('drift', [0, 1]);
    o.uDrift.value.set(d[0], d[1]);
    o.uLight.value = this.k('light', 0.8);
  }

  protected effect() {
    return /* glsl */ `
uniform int uMode; uniform float uCell, uLine, uHorizon, uTilt, uLight; uniform vec2 uDrift;

/** Hairline coverage of a grid in coordinates g (lines at whole numbers), uLine px wide, faded to its mean coverage
 * where the cells get too small to draw (no moire). */
float hairGrid(vec2 g, bool dots) {
  vec2 fw = max(fwidth(g), vec2(1e-5));
  vec2 d = abs(fract(g + 0.5) - 0.5);
  float lw = uLine * PX_SCALE;
  float cov;
  if (dots) {
    float r = length(d / fw);
    cov = sat(lw * 1.2 + 0.5 - r);
  } else {
    vec2 dpx = d / fw;
    vec2 l = clamp(0.5 * lw + 0.5 - dpx, 0.0, 1.0);
    cov = max(l.x, l.y);
  }
  // mean coverage of the same marks, where a cell spans only a few px
  vec2 m = clamp(lw * fw, 0.0, 1.0);
  float mean = min(dots ? 3.0 * m.x * m.y : m.x + m.y - m.x * m.y, 0.22);
  float k = smoothstep(0.06, 0.22, max(fw.x, fw.y));
  return mix(cov, mean, k);
}

vec4 effect(vec2 p, vec2 uv) {
  float t = uTime;
  vec3 acc = vec3(0.0);
  float cover = 0.0;
  if (uMode == 0) {
    vec2 q = rot2(uTilt * sin(t * 0.21 + uSeed)) * p;
    float hy = (uHorizon - 0.5) * uRes.y / min(uRes.x, uRes.y);
    float y = q.y - hy;
    float camH = 0.32;
    // (the grid is evaluated everywhere, outside any branch: its derivatives need every pixel of a quad)
    float z = camH / max(-y, 1e-3);
    vec2 g = vec2(q.x * z, z) / (0.5 * uCell * uScale) + uDrift * t * vec2(1.0, -1.0) + uSeed * 13.0;
    float line = hairGrid(g, false);
    float below = step(y, 0.0);
    // nearer lines are brighter; the far field dissolves into the horizon's haze
    float fog = exp(-z * 0.15) * below;
    float pool = 0.55 + 0.45 * exp(-q.x * q.x * 1.6);
    vec3 col = mix(uColor2, uColor, smoothstep(0.0, 6.0, z));
    acc += col * line * fog * pool * 0.95 * (1.0 + 1.3 * uPulse);
    cover = line * fog * 0.6;
    // the floor catches the horizon's light; the sky is a wash rising from it
    acc += below * uColor * 0.05 * exp(y / 0.05);
    acc += (1.0 - below) * uColor * 0.03 * exp(-y / 0.14);
    // the horizon: a hairline that runs hot, a bloom of haze around it
    float hz = abs(y);
    acc += ink1(0.65 + 0.35 * uPulse) * 0.5 * exp(-hz / (0.0025 * uScale));
    acc += uColor * 0.22 * exp(-hz / 0.035) * (1.0 + uPulse);
  } else {
    float cell = uCell * uScale / 12.0;
    vec2 g = p / cell + uDrift * t * vec2(1.0, -1.0) * 0.6 + uSeed * 13.0;
    float m = hairGrid(g, uMode == 1);
    // a pool of light drifting over the field
    vec2 c = 0.42 * vec2(sin(t * 0.17 + uSeed), cos(t * 0.13 + uSeed * 1.7)) * uRes / min(uRes.x, uRes.y);
    float pool = exp(-dot(p - c, p - c) / 0.18);
    vec3 col = mixD(C_FG_FAINT * 0.9, ink1(0.5 + 0.5 * uPulse), sat(uLight * pool * 1.3));
    acc += col * m * (0.7 + 0.6 * uPulse * pool);
    acc += uColor * 0.05 * pool * uLight;
    cover = m * 0.8;
  }
  return vec4(acc * uIntensity, sat(cover));
}`;
  }
}

export default Grid;
