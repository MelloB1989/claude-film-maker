// Light on the editor for `diff` (Plan 2 Task 16): the blood blade that strikes a line (Blade), soft glows (Halo: the
// impact's flare, the struck line's aura, the moss light that writes the new line), the diff's signs in the margin (Bar),
// the washes of the caret's row and the selection (Wash), the romance's pool of light (Spot), the studio wall behind it
// (Backdrop), and the camera's framing (fitKey).
//
// The Panel is unlit (its canvas is its colour), so everything that lights it is light added over its face: planes a
// hair in front of it, drawn after it (renderOrder) with additive blending and no depth write, so the depth of field
// reads the panel's depth under them. Only blood and moss glow, at glow() levels: bone washes stay far under the bloom.
import * as THREE from 'three';
import { glow, type GlowKey } from '../engine/look';
import { LIN } from '../engine/palette';
import type { CamKey, V3 } from '../engine/stage';

/** Drawn after the panel it lies on (its own renderOrder is 0). */
export const OVER = 2;

const additive = (u: Record<string, THREE.IUniform>, vertexShader: string, fragmentShader: string) =>
  new THREE.ShaderMaterial({ uniforms: u, vertexShader, fragmentShader, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });

const UV_VERT = /* glsl */ `varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;

/**
 * The blade: a line of blood light along a strike, from the line's first character (its tail) to the cut's leading
 * edge (its tip). Its core is a hairline as thick as the Panel's own strike, which it lies on; its light falls off
 * across it over a few px (the bloom carries it further). Hot, the tip burns at the strand's lit level and the light
 * runs back along the cut; cooled, the whole line is an ember just over the bloom's opening: a memory of the cut.
 *
 * In the panel's px (its group scales them): `set` takes the tail's x, the tip's x, the strike's centre y (px from the
 * panel's top), the heat (0..1) and the ember's level.
 */
export class Blade {
  mesh: THREE.Mesh;
  private u: Record<string, THREE.IUniform>;

  /** `core`: the hairline's half-thickness (px); `halo`: how far its light reaches across (px). */
  constructor(private panel: { w: number; h: number }, private core: number, private halo: number, key: GlowKey = 'blood') {
    this.u = {
      uColor: { value: new THREE.Vector3(...glow(key, 1)) },
      uLen: { value: 1 }, uHalf: { value: halo }, uCore: { value: core },
      uHot: { value: 3.6 }, uEmber: { value: 1.3 }, uHeat: { value: 0 }, uPad: { value: 0 },
    };
    const frag = /* glsl */ `
      uniform vec3 uColor; uniform float uLen, uHalf, uCore, uHot, uEmber, uHeat, uPad;
      varying vec2 vUv;
      void main() {
        float x = vUv.x * (uLen + uPad), y = (vUv.y - 0.5) * 2.0 * uHalf; // px from the tail along the cut, px across it
        float back = uLen - x;
        // the heat runs back along the cut from its edge, a few characters' worth; where it is hot the cut is thicker
        float run = exp(-max(back, 0.0) / max(1.0, 0.3 * uLen)) * uHeat;
        float core = uCore * (1.0 + 0.9 * run);
        float across = exp(-pow(abs(y) / core, 2.5)) + 0.16 * exp(-abs(y) / (0.35 * uHalf));
        float level = uEmber + (uHot - uEmber) * run;
        float ends = smoothstep(0.0, 2.0, x) * smoothstep(0.0, 1.5, back + 1.5);
        // the head: a white-hot spark at the cut's edge while it cuts, longer than it is tall, its light reaching past it
        vec2 hd = vec2(back / 7.0, y / (2.4 * uCore));
        float head = exp(-dot(hd, hd)) * uHeat * uHeat;
        gl_FragColor = vec4(uColor * (level * across * ends + 2.2 * uHot * head), 1.0);
      }`;
    const geo = new THREE.PlaneGeometry(1, 1);
    geo.translate(0.5, 0, 0);
    this.mesh = new THREE.Mesh(geo, additive(this.u, UV_VERT, frag));
    this.mesh.renderOrder = OVER;
    this.mesh.frustumCulled = false;
  }

  set(x0: number, x1: number, y: number, heat: number, ember: number, hot = 3.6) {
    const { w, h } = this.panel, pad = 14; // the plane reaches past the edge, for the head's light
    const len = Math.max(1e-3, x1 - x0);
    this.mesh.visible = x1 - x0 > 1.5;
    this.mesh.position.set((x0 - w / 2) / 1000, (h / 2 - y) / 1000, 0.6 / 1000);
    this.mesh.scale.set((len + pad) / 1000, (2 * this.halo) / 1000, 1);
    this.u.uPad!.value = pad;
    this.u.uLen!.value = len;
    this.u.uHeat!.value = heat;
    this.u.uEmber!.value = ember;
    this.u.uHot!.value = hot;
  }

  dispose() {
    this.mesh.geometry.dispose();
    (this.mesh.material as THREE.Material).dispose();
  }
}

/** A soft round light (blood or moss) on the panel: a mark's glow. In panel px; its level is a glow() level. */
export class Halo {
  mesh: THREE.Mesh;
  private u: Record<string, THREE.IUniform>;

  constructor(private panel: { w: number; h: number }, key: GlowKey, private r: number) {
    this.u = { uColor: { value: new THREE.Vector3(...glow(key, 1)) }, uLevel: { value: 0 } };
    const frag = /* glsl */ `
      uniform vec3 uColor; uniform float uLevel; varying vec2 vUv;
      void main() { vec2 d = (vUv - 0.5) * 2.0; float k = exp(-4.5 * dot(d, d)); gl_FragColor = vec4(uColor * uLevel * k * smoothstep(1.0, 0.8, length(d)), 1.0); }`;
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), additive(this.u, UV_VERT, frag));
    this.mesh.renderOrder = OVER;
    this.mesh.frustumCulled = false;
  }

  /** Centred at (x, y) px, its light at `level` (0: off), `r` px round (scale.x/y can be set apart after, for an oval). */
  set(x: number, y: number, level: number, r = this.r) {
    const { w, h } = this.panel;
    this.mesh.visible = level > 1e-3;
    this.mesh.position.set((x - w / 2) / 1000, (h / 2 - y) / 1000, 0.5 / 1000);
    this.mesh.scale.set((2 * r) / 1000, (2 * r) / 1000, 1);
    this.u.uLevel!.value = level;
  }

  dispose() {
    this.mesh.geometry.dispose();
    (this.mesh.material as THREE.Material).dispose();
  }
}

/**
 * A wash of bone light over a box on the panel (the caret's row, a selection): additive and faint, its edges a px
 * soft. Bone is added well under the bloom's opening, so it lifts the panel and its type without ever blooming.
 */
export class Wash {
  mesh: THREE.Mesh;
  private u: Record<string, THREE.IUniform>;

  constructor(private panel: { w: number; h: number }, rgb: readonly [number, number, number] = LIN.bone) {
    this.u = { uColor: { value: new THREE.Vector3(...rgb) }, uLevel: { value: 0 }, uSize: { value: new THREE.Vector2(1, 1) }, uEdge: { value: 0 } };
    const frag = /* glsl */ `
      uniform vec3 uColor; uniform float uLevel, uEdge; uniform vec2 uSize; varying vec2 vUv;
      void main() {
        vec2 p = vUv * uSize, q = min(p, uSize - p);
        float k = smoothstep(0.0, 1.2, min(q.x, q.y));
        float bar = uEdge * (1.0 - smoothstep(1.5, 3.5, p.x)); // a brighter edge at its left: where the caret stands
        gl_FragColor = vec4(uColor * (uLevel + bar) * k, 1.0);
      }`;
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), additive(this.u, UV_VERT, frag));
    this.mesh.renderOrder = OVER;
    this.mesh.frustumCulled = false;
  }

  /** The box from (x0, y0) to (x1, y1) px, its wash at `level` (a fraction of bone), its left edge lit by `edge`. */
  set(x0: number, y0: number, x1: number, y1: number, level: number, edge = 0) {
    const { w, h } = this.panel, bw = Math.max(1e-3, x1 - x0), bh = Math.max(1e-3, y1 - y0);
    this.mesh.visible = level > 1e-4 && x1 - x0 > 0.25;
    this.mesh.position.set((x0 + bw / 2 - w / 2) / 1000, (h / 2 - (y0 + bh / 2)) / 1000, 0.4 / 1000);
    this.mesh.scale.set(bw / 1000, bh / 1000, 1);
    this.u.uLevel!.value = level;
    this.u.uEdge!.value = edge;
    (this.u.uSize!.value as THREE.Vector2).set(bw, bh);
  }

  dispose() {
    this.mesh.geometry.dispose();
    (this.mesh.material as THREE.Material).dispose();
  }
}

/**
 * A diff's sign in the editor's left margin (as gitsigns draws it): a slim bar the height of its row, lit blood or moss
 * at a glow() level. In panel px.
 */
export class Bar {
  mesh: THREE.Mesh;
  private u: Record<string, THREE.IUniform>;

  constructor(private panel: { w: number; h: number }, key: GlowKey) {
    this.u = { uColor: { value: new THREE.Vector3(...glow(key, 1)) }, uLevel: { value: 0 }, uSize: { value: new THREE.Vector2(1, 1) } };
    const frag = /* glsl */ `
      uniform vec3 uColor; uniform float uLevel; uniform vec2 uSize; varying vec2 vUv;
      void main() {
        vec2 p = (vUv - 0.5) * uSize; // px from its centre
        float core = 1.0 - smoothstep(1.0, 1.8, abs(p.x)), ends = 1.0 - smoothstep(0.5 * uSize.y - 6.0, 0.5 * uSize.y - 4.0, abs(p.y));
        float halo = exp(-abs(p.x) / 2.5) * 0.18;
        gl_FragColor = vec4(uColor * uLevel * (core + halo) * ends, 1.0);
      }`;
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), additive(this.u, UV_VERT, frag));
    this.mesh.renderOrder = OVER;
    this.mesh.frustumCulled = false;
  }

  /** At x px, over the row from y0 to y1, its light at `level` (0: off). */
  set(x: number, y0: number, y1: number, level: number) {
    const { w, h } = this.panel, bw = 14, bh = Math.max(1e-3, y1 - y0);
    this.mesh.visible = level > 1e-3 && bh > 1;
    this.mesh.position.set((x - w / 2) / 1000, (h / 2 - (y0 + y1) / 2) / 1000, 0.5 / 1000);
    this.mesh.scale.set(bw / 1000, bh / 1000, 1);
    this.u.uLevel!.value = level;
    (this.u.uSize!.value as THREE.Vector2).set(bw, bh);
  }

  dispose() {
    this.mesh.geometry.dispose();
    (this.mesh.material as THREE.Material).dispose();
  }
}

/**
 * The romance's light on the editor: a pool round the diff's two lines, warm (bone with a breath of blood: the light
 * the ember gives), and the rest of the panel falling into shadow (ink over it, premultiplied: what is outside the pool
 * darkens, what is in it is lit). In panel px; `set` takes the pool's centre and radii and its strength.
 */
export class Spot {
  mesh: THREE.Mesh;
  private u: Record<string, THREE.IUniform>;

  constructor(private panel: { w: number; h: number }) {
    const warm = LIN.bone.map((c, i) => 0.72 * c + 0.28 * LIN.blood[i]!) as [number, number, number];
    this.u = {
      uWarm: { value: new THREE.Vector3(...warm) }, uInk: { value: new THREE.Vector3(...LIN.ink) },
      uCentre: { value: new THREE.Vector2() }, uRadius: { value: new THREE.Vector2(1, 1) }, uLevel: { value: 0 }, uSize: { value: new THREE.Vector2(panel.w, panel.h) },
    };
    const frag = /* glsl */ `
      uniform vec3 uWarm, uInk; uniform vec2 uCentre, uRadius, uSize; uniform float uLevel; varying vec2 vUv;
      void main() {
        vec2 p = vec2(vUv.x, 1.0 - vUv.y) * uSize, d = (p - uCentre) / uRadius;
        float pool = exp(-dot(d, d));
        float dark = uLevel * 0.62 * (1.0 - pool);
        gl_FragColor = vec4(uWarm * uLevel * 0.05 * pool + uInk * dark, dark);
      }`;
    const m = new THREE.ShaderMaterial({ uniforms: this.u, vertexShader: UV_VERT, fragmentShader: frag, transparent: true, depthWrite: false });
    m.blending = THREE.CustomBlending;
    m.blendEquation = THREE.AddEquation;
    m.blendSrc = THREE.OneFactor;
    m.blendDst = THREE.OneMinusSrcAlphaFactor;
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry(panel.w / 1000, panel.h / 1000), m);
    this.mesh.position.z = 0.3 / 1000;
    this.mesh.renderOrder = OVER + 1;
    this.mesh.frustumCulled = false;
  }

  set(cx: number, cy: number, rx: number, ry: number, level: number) {
    this.mesh.visible = level > 1e-3;
    (this.u.uCentre!.value as THREE.Vector2).set(cx, cy);
    (this.u.uRadius!.value as THREE.Vector2).set(rx, ry);
    this.u.uLevel!.value = level;
  }

  dispose() {
    this.mesh.geometry.dispose();
    (this.mesh.material as THREE.Material).dispose();
  }
}

/**
 * The studio behind the editor: a wide plane far back whose ink lifts softly toward `lift` in a pool (unlit and
 * opaque, so the depth of field reads it as the far distance). The romance warms it: the pool comes up behind the
 * struck line.
 */
export class Backdrop {
  mesh: THREE.Mesh;
  private u: Record<string, THREE.IUniform>;

  constructor(size: [number, number]) {
    this.u = {
      uInk: { value: new THREE.Vector3(...LIN.ink) }, uLift: { value: new THREE.Vector3(...LIN.panel2) },
      uCentre: { value: new THREE.Vector2() }, uRadius: { value: new THREE.Vector2(1, 1) }, uLevel: { value: 0 },
    };
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry(size[0], size[1]), new THREE.ShaderMaterial({
      uniforms: this.u,
      vertexShader: /* glsl */ `varying vec2 vP; void main() { vP = position.xy; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
      fragmentShader: /* glsl */ `uniform vec3 uInk, uLift; uniform vec2 uCentre, uRadius; uniform float uLevel; varying vec2 vP;
        void main() { vec2 d = (vP - uCentre) / uRadius; gl_FragColor = vec4(mix(uInk, uLift, uLevel * exp(-dot(d, d))), 1.0); }`,
    }));
  }

  /** The pool's centre and radii (the plane's own units) and its strength (0: plain ink). */
  set(cx: number, cy: number, rx: number, ry: number, level: number) {
    (this.u.uCentre!.value as THREE.Vector2).set(cx, cy);
    (this.u.uRadius!.value as THREE.Vector2).set(rx, ry);
    this.u.uLevel!.value = level;
  }

  dispose() {
    this.mesh.geometry.dispose();
    (this.mesh.material as THREE.Material).dispose();
  }
}

// ---------------------------------------------------------------------------------------------------- framing

export interface Fit {
  /** Degrees round the subject's y axis from its front (+z): + to its right. */
  az: number;
  /** Degrees above it. */
  el: number;
  fov: number;
  /** Fraction of the half-frame left empty each side, across and up. */
  margin?: [number, number];
  /** Where the box sits, in fractions of the half-frame (+x right, +y up). */
  bias?: [number, number];
  roll?: number;
}

/**
 * A camera key that fits world points in frame from a direction, to a margin, placed by `bias`: projected, measured in
 * the view's plane, the distance scaled and the target shifted until the framing holds (perspective makes one pass
 * inexact). `frame` is the subject's frame (its right, up and front in the world): az and el are taken in it.
 */
export function fitKey(t: number, pts: readonly THREE.Vector3[], o: Fit, frame: THREE.Matrix4, ease?: (x: number) => number): CamKey {
  const [mx, my] = o.margin ?? [0.12, 0.12];
  const [bx, by] = o.bias ?? [0, 0];
  const az = THREE.MathUtils.degToRad(o.az), el = THREE.MathUtils.degToRad(o.el);
  const R = new THREE.Vector3(), U = new THREE.Vector3(), Fz = new THREE.Vector3();
  frame.extractBasis(R, U, Fz);
  const back = Fz.clone().multiplyScalar(Math.cos(az) * Math.cos(el)).addScaledVector(R, Math.sin(az) * Math.cos(el)).addScaledVector(U, Math.sin(el)).normalize();
  const f = back.clone().negate();
  const r = new THREE.Vector3().crossVectors(f, new THREE.Vector3(0, 1, 0)).normalize();
  const u = new THREE.Vector3().crossVectors(r, f);
  const ty = Math.tan(THREE.MathUtils.degToRad(o.fov) / 2), tx = ty * (16 / 9);
  const centre = pts.reduce((a, p) => a.add(p), new THREE.Vector3()).divideScalar(Math.max(1, pts.length));
  let D = 1;
  for (let it = 0; it < 32; it++) {
    const cam = centre.clone().addScaledVector(back, D);
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const p of pts) {
      const v = p.clone().sub(cam), z = v.dot(f);
      const x = v.dot(r) / z, y = v.dot(u) / z;
      x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
    }
    const s = Math.max((x1 - x0) / (2 * tx * (1 - mx) * (1 - Math.abs(bx))), (y1 - y0) / (2 * ty * (1 - my) * (1 - Math.abs(by))));
    const cx = (x0 + x1) / 2 - bx * tx * (1 - mx) * s, cy = (y0 + y1) / 2 - by * ty * (1 - my) * s;
    centre.addScaledVector(r, cx * D).addScaledVector(u, cy * D);
    D *= s;
  }
  const pos = centre.clone().addScaledVector(back, D);
  return { t, pos: pos.toArray() as V3, target: centre.toArray() as V3, fov: o.fov, roll: o.roll, ease };
}
