// Atmosphere for anime shots, each one fullscreen GLSL pass and a pure function of time (BgScene: `color`, `intensity`,
// `scale`, `speed`, `seed`, `clock`), transparent by default so it stacks over a picture or plays as an overlay:
//
//   Mist   drifting banks of fog in a horizontal band, and a veil over the whole frame
//          band 0.35 (the band's centre, from the bottom), width 0.25, drift [0.03, 0], veil 0.08, softness 1
//   Smoke  a thin wisp curling up from a point (a pipe, incense, a doused fire)
//          origin [0.5, 0.4] (uv, from the bottom left), height 0.5 (short sides it rises), wind 0.08, width 1
//   Rays   shafts of light from a source (the sun breaking through), added as light, with dust motes in them
//          source [0.6, 1.1] (uv), toward [0.5, 0.0], spread 0.5, motes 1
//   Paper  the grain of the paper a picture is painted on: fibres, mottling and a darker edge, as a wash of `color`
//          over the frame (an overlay over a whole film): fibres 1, mottle 1, edge 0.35
import * as THREE from 'three';
import { BgScene } from '../bg/base';
import type { Frame } from '../../engine/scene';

const v2 = (a: [number, number]) => new THREE.Vector2(a[0], a[1]);

export class Mist extends BgScene {
  protected override defaults = { background: 'none', color: '#d9dde3', speed: 1 } as Record<string, unknown>;
  private u = { uBand: { value: 0.35 }, uWidth: { value: 0.25 }, uDrift: { value: new THREE.Vector2(0.03, 0) }, uVeil: { value: 0.08 }, uSoft: { value: 1 } };
  protected override uniforms() {
    return this.u;
  }
  protected effect() {
    return /* glsl */ `
uniform float uBand, uWidth, uVeil, uSoft; uniform vec2 uDrift;
vec4 effect(vec2 p, vec2 uv) {
  vec2 q = p * 1.3 / uScale;
  float n1 = 0.5 + 0.5 * fbm(q + uDrift * uTime * 9.0 + vec2(uSeed * 5.1, 0.0), 5);
  float n2 = 0.5 + 0.5 * fbm(q * 2.2 - uDrift * uTime * 5.0 + vec2(7.3, uSeed), 4);
  float band = exp(-pow((uv.y - uBand) / max(uWidth, 1e-3), 2.0));
  float m = smoothstep(0.4 - 0.15 * uSoft, 0.85, 0.7 * n1 + 0.3 * n2) * band;
  m = sat((m * 0.85 + uVeil * (0.6 + 0.4 * n2)) * uIntensity);
  return vec4(uColor * m, m);
}`;
  }
  protected override update() {
    this.u.uBand.value = this.k('band', 0.35);
    this.u.uWidth.value = this.k('width', 0.25);
    this.u.uDrift.value = v2(this.k<[number, number]>('drift', [0.03, 0]));
    this.u.uVeil.value = this.k('veil', 0.08);
    this.u.uSoft.value = this.k('softness', 1);
  }
}

export class Smoke extends BgScene {
  protected override defaults = { background: 'none', color: '#e6e8ec', speed: 1 } as Record<string, unknown>;
  private u = { uOrigin: { value: new THREE.Vector2(0.5, 0.4) }, uHeight: { value: 0.5 }, uWind: { value: 0.08 }, uWidth: { value: 1 } };
  protected override uniforms() {
    return this.u;
  }
  protected effect() {
    return /* glsl */ `
uniform vec2 uOrigin; uniform float uHeight, uWind, uWidth;
vec4 effect(vec2 p, vec2 uv) {
  vec2 o = (uOrigin - 0.5) * uRes / min(uRes.x, uRes.y);
  vec2 d = p - o;
  float h = d.y;
  if (h < -0.02) return vec4(0.0);
  float t = uTime;
  // the wisp's centre line: carried by the wind, curling more as it rises
  float cx = uWind * h * (1.0 + h) + 0.035 * h * 2.4 * sin(h * 11.0 - t * 1.6 + uSeed) + 0.025 * snoise(vec2(h * 2.5 - t * 0.35, uSeed * 3.0));
  float w = (0.003 + 0.06 * h * h + 0.02 * h) * uWidth;
  float x = (d.x - cx) / w;
  float core = exp(-x * x);
  // it breaks into curls and threads as it rises
  float turb = 0.5 + 0.5 * fbm(vec2(d.x * 14.0 - cx * 14.0, h * 9.0 - t * 1.1) + uSeed * 1.7, 4);
  float threads = mix(1.0, smoothstep(0.35, 0.75, turb), sat(h * 4.0));
  float fade = smoothstep(-0.02, 0.01, h) * exp(-h / max(0.05, uHeight * 0.45));
  float m = sat(core * threads * fade * 0.85 * uIntensity);
  return vec4(uColor * m, m);
}`;
  }
  protected override update() {
    this.u.uOrigin.value = v2(this.k<[number, number]>('origin', [0.5, 0.4]));
    this.u.uHeight.value = this.k('height', 0.5);
    this.u.uWind.value = this.k('wind', 0.08);
    this.u.uWidth.value = this.k('width', 1);
  }
}

export class Rays extends BgScene {
  protected override defaults = { background: 'none', color: '#ffd9a0', speed: 1 } as Record<string, unknown>;
  private u = { uSource: { value: new THREE.Vector2(0.6, 1.1) }, uToward: { value: new THREE.Vector2(0.5, 0) }, uSpread: { value: 0.5 }, uMotes: { value: 1 } };
  protected override uniforms() {
    return this.u;
  }
  protected effect() {
    return /* glsl */ `
uniform vec2 uSource, uToward; uniform float uSpread, uMotes;
vec4 effect(vec2 p, vec2 uv) {
  vec2 asp = uRes / min(uRes.x, uRes.y);
  vec2 s = (uSource - 0.5) * asp, tw = (uToward - 0.5) * asp;
  vec2 d = p - s;
  float r = length(d);
  vec2 axis = normalize(tw - s);
  float ang = atan(d.y, d.x) - atan(axis.y, axis.x);
  ang = atan(sin(ang), cos(ang));
  float cone = exp(-pow(ang / max(0.05, uSpread), 2.0));
  float t = uTime;
  float shafts = 0.55 * (0.5 + 0.5 * snoise(vec2(ang * 7.0, t * 0.06 + uSeed)))
               + 0.45 * (0.5 + 0.5 * snoise(vec2(ang * 19.0, t * 0.09 + 3.0 + uSeed)));
  shafts = pow(sat(shafts), 2.5);
  float fall = exp(-r * 0.55);
  float light = shafts * cone * fall;
  // dust motes drifting in the light
  vec2 g = p * 26.0 + vec2(t * 0.05, t * 0.12);
  vec2 c = floor(g), f = fract(g) - 0.5;
  vec2 o = (hash22(c + uSeed) - 0.5) * 0.7;
  float tw2 = 0.5 + 0.5 * sin(t * (1.0 + 2.0 * hash12(c)) + 6.28 * hash12(c + 3.0));
  float mote = exp(-dot(f - o, f - o) * 260.0) * step(0.82, hash12(c + 9.0)) * tw2;
  light += mote * cone * fall * 1.6 * uMotes;
  float m = light * uIntensity;
  return vec4(uColor * m, 0.0);   // light: it adds, it covers nothing
}`;
  }
  protected override update() {
    this.u.uSource.value = v2(this.k<[number, number]>('source', [0.6, 1.1]));
    this.u.uToward.value = v2(this.k<[number, number]>('toward', [0.5, 0]));
    this.u.uSpread.value = this.k('spread', 0.5);
    this.u.uMotes.value = this.k('motes', 1);
  }
}

export class Paper extends BgScene {
  protected override defaults = { background: 'none', color: '#2a2118', speed: 0 } as Record<string, unknown>;
  private u = { uFibres: { value: 1 }, uMottle: { value: 1 }, uEdge: { value: 0.35 }, uStep: { value: 0 } };
  protected override uniforms() {
    return this.u;
  }
  protected effect() {
    return /* glsl */ `
uniform float uFibres, uMottle, uEdge, uStep;
vec4 effect(vec2 p, vec2 uv) {
  // the paper doesn't move with the picture; its grain jitters a little each drawing (on twos: 12 a second)
  vec2 j = (hash22(vec2(uStep, uSeed)) - 0.5) * 0.002;
  vec2 q = p + j;
  float mottle = 0.5 + 0.5 * fbm(q * 3.0 + uSeed, 4);
  float fib = 0.0;
  for (int i = 0; i < 3; i++) {
    float a = 0.7 * float(i) + uSeed;
    vec2 r = rot2(a) * q;
    fib += pow(sat(0.5 + 0.5 * snoise(vec2(r.x * 3.0, r.y * 95.0 + float(i) * 13.0))), 6.0);
  }
  float edge = pow(sat(length((uv - 0.5) * vec2(1.0, 0.9)) * 1.35), 2.6);
  float m = sat((0.05 * uMottle * mottle + 0.035 * uFibres * fib + uEdge * 0.25 * edge) * uIntensity);
  return vec4(uColor * m, m);
}`;
  }
  protected override update(f: Frame) {
    this.u.uFibres.value = this.k('fibres', 1);
    this.u.uMottle.value = this.k('mottle', 1);
    this.u.uEdge.value = this.k('edge', 0.35);
    this.u.uStep.value = Math.floor(f.t * 12);
  }
}
