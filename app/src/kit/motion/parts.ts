// The v3 building blocks (docs/STYLE_V3.md §10): kinetic 3D type, flat labels in space, packet flows, beams, slabs, and
// the environment (floor, haze, dust). Each is built once in a scene's build() and posed per frame from the shot clock
// by its pose(t): nothing carries state between frames.
//
// Everything that glows is an opaque MeshBasicMaterial in HDR colour (toneMapped off): it writes depth, so the depth of
// field blurs it where it stands, and the post's bloom (chroma-gated: only coloured light blooms) gives it its halo.
import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js';
import { Mat, Type3D } from '../../engine/type3d';
import { F } from '../../engine/type';
import { LIN, type PaletteKey } from '../../engine/palette';
import { clamp, ease, hash, mulberry32, TAU } from '../../engine/util';
import { antic, hdr, pulse, spring, win } from './fns';

// ———————————————————————————————————————————————————————————————————————————————————————————————— materials

/** An unlit material in HDR colour: `k` > 1 on an accent blooms. */
export function glowMat(role: PaletteKey | `#${string}`, k = 3): THREE.MeshBasicMaterial {
  return new THREE.MeshBasicMaterial({ color: hdr(role, k), toneMapped: false });
}
/** Flat warm white for labels (unlit, so it reads at any light level). */
export function inkMat(role: PaletteKey | `#${string}` = 'fg', k = 1): THREE.MeshBasicMaterial {
  return new THREE.MeshBasicMaterial({ color: hdr(role, k), transparent: true });
}
/** The matte object surface (servers, boxes, slabs): a dark warm physical material with a clearcoat for sweeps. */
export function surfaceMat(role: PaletteKey | `#${string}` = 'surface', o: { rough?: number; coat?: number; k?: number } = {}): THREE.MeshPhysicalMaterial {
  return new THREE.MeshPhysicalMaterial({
    color: hdr(role, o.k ?? 1), roughness: o.rough ?? 0.42, metalness: 0.1, clearcoat: o.coat ?? 0.6, clearcoatRoughness: 0.18,
  });
}

/**
 * Solid accent for hero type and objects: the accent as the surface colour with an emissive glow of `glowK` (the face
 * reads as lit colour and blooms softly), a clearcoat for the studio's sweeps. emphasis() pulses its emissive.
 */
export function accentSolid(role: PaletteKey | `#${string}` = 'accent', glowK = 1.2): THREE.MeshPhysicalMaterial {
  const m = new THREE.MeshPhysicalMaterial({ color: hdr(role, 1), roughness: 0.35, metalness: 0, clearcoat: 0.8, clearcoatRoughness: 0.15 });
  m.emissive.copy(hdr(role, 1));
  m.emissiveIntensity = glowK;
  return m;
}

// ———————————————————————————————————————————————————————————————————————————————————————————————— kinetic type

export type Entrance = 'rise' | 'slam' | 'flip' | 'type' | 'drop';

export interface KineticOpts {
  family?: string;
  /** World units per em. */
  size: number;
  depth?: number;
  bevel?: number;
  tracking?: number;
  /** Words (0-based, split by white space) drawn in the accent material. */
  accentWords?: number[];
  /** Materials: the line's, the accent words'. Defaults: satin bone, Mat.accent('accent'). */
  mat?: THREE.Material;
  accentMat?: THREE.MeshPhysicalMaterial;
  /** 'left' | 'center' | 'right' alignment about the group's origin. */
  align?: 'left' | 'center' | 'right';
}

/**
 * A line of extruded type whose glyphs arrive on cue: `enter(t, at, kind)` poses every glyph for time t of an entrance
 * starting at `at` (seconds, shot clock). Per-word timing: `at` may be an array, one start per word (the VO words).
 */
export class KineticText {
  readonly type: Type3D;
  readonly group = new THREE.Group();
  readonly accentMat: THREE.MeshPhysicalMaterial | null;
  private baseEmissive: number;

  constructor(text: string, o: KineticOpts) {
    const family = o.family ?? F.display(100, 800);
    const mat = o.mat ?? Mat.satinBone();
    this.accentMat = o.accentWords?.length ? o.accentMat ?? Mat.accent('accent') : null;
    this.baseEmissive = this.accentMat?.emissiveIntensity ?? 0;
    this.type = new Type3D(text, { family, size: o.size, depth: o.depth, bevel: o.bevel, tracking: o.tracking }, (g) =>
      this.accentMat && o.accentWords!.includes(g.word) ? this.accentMat : mat);
    const off = o.align === 'center' ? -this.type.width / 2 : o.align === 'right' ? -this.type.width : 0;
    this.type.group.position.x = off;
    this.group.add(this.type.group);
  }

  get width() { return this.type.width; }
  get size() { return this.type.size; }

  /**
   * Pose an entrance. `at`: one start for the line (glyphs stagger by `step` s) or one per word. Returns 0..1, how far
   * the line has arrived (for linked moves).
   */
  enter(t: number, at: number | number[], kind: Entrance = 'rise', step = 1.2 / 24): number {
    const s = this.type.size;
    let done = 1;
    let wordIdx = -1, inWord = 0;
    this.type.glyphs.forEach((g, i) => {
      if (g.word !== wordIdx) (wordIdx = g.word), (inWord = 0);
      const t0 = Array.isArray(at) ? (at[g.word] ?? at[at.length - 1]!) + inWord * step * 0.6 : at + i * step;
      inWord++;
      const m = g.mesh;
      m.position.copy(g.home);
      m.rotation.set(0, 0, 0);
      let sc = 1;
      if (kind === 'rise') {
        const k = spring(t, t0, 0.5, 0.1);
        m.position.y += (1 - k) * -0.75 * s;
        m.position.z += (1 - k) * -0.2 * s;
        m.rotation.x = (1 - k) * -1.25;
        sc = clamp(k * 1.4);
      } else if (kind === 'drop') {
        const k = spring(t, t0, 0.45, 0.14);
        m.position.y += (1 - k) * 0.9 * s;
        m.rotation.x = (1 - k) * 0.9;
        sc = clamp(k * 1.6);
      } else if (kind === 'slam') {
        const k = win(t, t0, 0.12);
        const sp = spring(t, t0 + 0.06, 0.42, 0.12);
        sc = t < t0 ? 0 : k < 1 ? 2.2 - 1.2 * ease.outCubic(k) : 1 + (1 - sp) * 0.25 * Math.cos(sp * 3);
        m.position.z += t < t0 ? 0 : (1 - ease.outExpo(k)) * 1.2 * s;
      } else if (kind === 'flip') {
        const k = spring(t, t0, 0.5, 0.08);
        m.rotation.y = (1 - k) * (Math.PI / 2);
        sc = t < t0 ? 0 : 1;
      } else if (kind === 'type') {
        sc = t < t0 ? 0 : 1 + 0.25 * pulse(t, t0, 0.01, 0.05);
      }
      m.scale.setScalar(s * Math.max(0, sc));
      m.visible = sc > 0.001;
      done = Math.min(done, clamp((t - t0) / 0.3));
    });
    return done;
  }

  /** Emphasis on the accent words: the rim glow flashes up at `at` (call after enter; adds a scale kick). */
  emphasis(t: number, at: number, amt = 1) {
    const p = pulse(t, at, 0.05, 0.18) * amt;
    if (this.accentMat) this.accentMat.emissiveIntensity = this.baseEmissive * (1 + 1.6 * p);
    const s = this.type.size;
    for (const g of this.type.glyphs) if (this.accentMat && g.mesh.material === this.accentMat) g.mesh.scale.multiplyScalar(1 + 0.08 * p), g.mesh.position.y += 0.02 * s * p;
  }

  /** An exit toward the camera: glyphs fly forward (through the focus plane) and shrink away from `at`. */
  exit(t: number, at: number, dur = 0.35) {
    if (t < at) return;
    const s = this.type.size;
    this.type.glyphs.forEach((g, i) => {
      const k = ease.inCubic(win(t, at + i * 0.01, dur));
      g.mesh.position.z += k * 3 * s;
      g.mesh.position.y += k * (hash(i, 3) - 0.5) * s;
      g.mesh.scale.multiplyScalar(1 - k);
      if (k >= 1) g.mesh.visible = false;
    });
  }

  dispose() { this.type.dispose(); }
}

/** Flat type in space (Geist / Mono labels): Type3D with a hairline depth in an unlit material, crisp at any light. */
export class Label {
  readonly kt: KineticText;
  readonly mat: THREE.MeshBasicMaterial;
  constructor(text: string, o: { size: number; family?: string; role?: PaletteKey | `#${string}`; k?: number; align?: 'left' | 'center' | 'right'; tracking?: number }) {
    this.mat = inkMat(o.role ?? 'fg', o.k ?? 1);
    this.kt = new KineticText(text, { family: o.family ?? F.ui(600), size: o.size, depth: 0.03, bevel: 0.002, mat: this.mat, align: o.align ?? 'center', tracking: o.tracking });
  }
  get group() { return this.kt.group; }
  get width() { return this.kt.width; }
  /** Pose: arrive at `at` (rise by default) and fade with `alpha`. */
  pose(t: number, at: number | number[], kind: Entrance = 'rise', alpha = 1) {
    this.mat.opacity = alpha;
    this.kt.enter(t, at, kind, 0.6 / 24);
    this.group.visible = alpha > 0.002;
  }
  dispose() { this.kt.dispose(); this.mat.dispose(); }
}

// ———————————————————————————————————————————————————————————————————————————————————————————————— flows and beams

export interface FlowOpts {
  /** Packets per second leaving the start. */
  rate: number;
  /** World units per second. */
  speed: number;
  /** Capsule radius and length (world units, at rest). */
  radius?: number;
  length?: number;
  /** Colour roles and HDR level of the packets (a share `hotShare` of them in `hot`). */
  role?: PaletteKey | `#${string}`;
  hot?: PaletteKey | `#${string}`;
  k?: number;
  hotShare?: number;
  /** Lateral scatter of a packet's lane (world units) and speed variety (0..1). */
  spread?: number;
  vary?: number;
  /** Max packets alive (instances). */
  max?: number;
  seed?: number;
}

/**
 * A stream of glowing capsules along a curve. pose(t, from, until) shows the packets that left between `from` and
 * `until` (s) and are still on the way at t; `density` (0..1, or a function of departure time) thins the stream.
 */
export class Flow {
  readonly mesh: THREE.InstancedMesh;
  private len: number;
  private o: Required<FlowOpts>;
  private frames: { T: THREE.Vector3[]; N: THREE.Vector3[]; B: THREE.Vector3[] };
  private dummy = new THREE.Object3D();
  private mat: THREE.MeshBasicMaterial;
  private cols: THREE.Color[] = [];

  constructor(readonly curve: THREE.Curve<THREE.Vector3>, o: FlowOpts) {
    this.o = {
      radius: 0.02, length: 0.12, role: 'accent', hot: 'accentBright', k: 4, hotShare: 0.3, spread: 0, vary: 0.25, max: 160, seed: 1, ...o,
    } as Required<FlowOpts>;
    this.len = curve.getLength();
    const geo = new THREE.CapsuleGeometry(1, 1, 4, 10);
    geo.rotateZ(Math.PI / 2); // along +x
    this.mat = new THREE.MeshBasicMaterial({ color: 0xffffff, toneMapped: false });
    this.mesh = new THREE.InstancedMesh(geo, this.mat, this.o.max);
    this.mesh.frustumCulled = false;
    const cA = hdr(this.o.role, this.o.k), cB = hdr(this.o.hot, this.o.k * 1.6);
    const rnd = mulberry32(this.o.seed);
    for (let i = 0; i < this.o.max; i++) this.cols.push(rnd() < this.o.hotShare ? cB : cA);
    for (let i = 0; i < this.o.max; i++) this.mesh.setColorAt(i, this.cols[i]!);
    const fr = curve.computeFrenetFrames(199, false);
    this.frames = { T: fr.tangents, N: fr.normals, B: fr.binormals };
  }

  private frameAt(u: number) {
    const i = Math.min(199, Math.max(0, Math.round(u * 199)));
    return { T: this.frames.T[i]!, N: this.frames.N[i]!, B: this.frames.B[i]! };
  }

  /**
   * Pose for time t: packets depart at from + n / rate (n = 0, 1, ...) up to `until`; each travels the curve at its
   * speed. `density(dep)` 0..1 keeps that share of departures. `fadeEnds` shrinks packets near both ends.
   */
  pose(t: number, from: number, until = Infinity, density: number | ((dep: number) => number) = 1, speedMul = 1) {
    const { rate, speed, radius, length, spread, vary, max, seed } = this.o;
    const travel = this.len / (speed * speedMul * (1 - vary * 0.5));
    const nFirst = Math.max(0, Math.floor((t - travel - from) * rate));
    const nLast = Math.floor((Math.min(t, until) - from) * rate);
    let k = 0;
    const d = this.dummy;
    for (let n = nFirst; n <= nLast && k < max; n++) {
      const dep = from + n / rate;
      if (dep > t || dep > until) break;
      const keep = typeof density === 'function' ? density(dep) : density;
      if (hash(n, seed) > keep) continue;
      const sp = speed * speedMul * (1 - vary * hash(n, seed + 7));
      const u = ((t - dep) * sp) / this.len;
      if (u < 0 || u > 1) continue;
      const p = this.curve.getPointAt(u);
      const { T, N, B } = this.frameAt(u);
      if (spread > 0) {
        const a = hash(n, seed + 3) * TAU, r = Math.sqrt(hash(n, seed + 5)) * spread;
        p.addScaledVector(N, Math.cos(a) * r).addScaledVector(B, Math.sin(a) * r);
      }
      const ends = Math.min(1, u / 0.04, (1 - u) / 0.04);
      const stretch = 1 + 0.6 * (sp / speed - 0.5);
      d.position.copy(p);
      d.quaternion.setFromUnitVectors(new THREE.Vector3(1, 0, 0), T);
      d.scale.set(length * 0.5 * stretch * ends + radius, radius * ends, radius * ends);
      d.updateMatrix();
      this.mesh.setMatrixAt(k, d.matrix);
      // the colour slot follows the packet, not the instance index, so a packet keeps its colour
      this.mesh.setColorAt(k, this.cols[n % max]!);
      k++;
    }
    this.mesh.count = k;
    this.mesh.instanceMatrix.needsUpdate = true;
    if (this.mesh.instanceColor) this.mesh.instanceColor.needsUpdate = true;
    return k;
  }

  dispose() { this.mesh.geometry.dispose(); this.mat.dispose(); this.mesh.dispose(); }
}

/** A glowing tube along a curve that draws on: pose(t, at, dur) reveals it from its start (or both ends, `from`). */
export class Beam {
  readonly mesh: THREE.Mesh;
  readonly mat: THREE.MeshBasicMaterial;
  private segs: number;
  private radial: number;
  private base: THREE.Color;

  constructor(readonly curve: THREE.Curve<THREE.Vector3>, o: { radius?: number; role?: PaletteKey | `#${string}`; k?: number; segments?: number } = {}) {
    this.segs = o.segments ?? 160;
    this.radial = 8;
    const geo = new THREE.TubeGeometry(curve, this.segs, o.radius ?? 0.008, this.radial, false);
    this.base = hdr(o.role ?? 'accent', o.k ?? 2);
    this.mat = new THREE.MeshBasicMaterial({ color: this.base.clone(), toneMapped: false });
    this.mesh = new THREE.Mesh(geo, this.mat);
  }

  /** Reveal 0..1 of the length by time t (outExpo through [at, at + dur]); `glow` scales the colour (pulses). */
  pose(t: number, at: number, dur = 0.5, glowMul = 1) {
    const k = ease.outCubic(win(t, at, dur));
    const segs = Math.floor(k * this.segs);
    this.mesh.geometry.setDrawRange(0, segs * this.radial * 6);
    this.mesh.visible = segs > 0;
    this.mat.color.copy(this.base).multiplyScalar(glowMul);
    return k;
  }

  dispose() { this.mesh.geometry.dispose(); this.mat.dispose(); }
}

// ———————————————————————————————————————————————————————————————————————————————————————————————— slabs

/** A rounded box in the matte surface, with an optional glowing strip (an LED line) on its front face. */
export class Slab {
  readonly group = new THREE.Group();
  readonly body: THREE.Mesh;
  readonly mat: THREE.MeshPhysicalMaterial;
  readonly strip: THREE.Mesh | null = null;
  readonly stripMat: THREE.MeshBasicMaterial | null = null;

  constructor(w: number, h: number, d: number, o: { radius?: number; role?: PaletteKey | `#${string}`; strip?: PaletteKey | `#${string}`; stripK?: number; rough?: number } = {}) {
    this.mat = surfaceMat(o.role ?? 'surface', { rough: o.rough });
    this.body = new THREE.Mesh(new RoundedBoxGeometry(w, h, d, 4, o.radius ?? Math.min(w, h, d) * 0.12), this.mat);
    this.group.add(this.body);
    if (o.strip) {
      this.stripMat = glowMat(o.strip, o.stripK ?? 4);
      this.strip = new THREE.Mesh(new THREE.BoxGeometry(w * 0.7, Math.min(h * 0.04, 0.02), 0.004), this.stripMat);
      this.strip.position.set(0, -h * 0.36, d / 2 + 0.002);
      this.group.add(this.strip);
    }
  }

  /** Arrive with anticipation and a springy scale at `at`; returns the scale factor. */
  pop(t: number, at: number, from = 0): number {
    const k = antic(t, at, { amt: 0.06, settle: 0.5, over: 0.1 });
    const s = from + (1 - from) * k;
    this.group.scale.setScalar(Math.max(0.0001, s));
    this.group.visible = s > 0.001;
    return s;
  }

  dispose() {
    this.body.geometry.dispose(); this.mat.dispose();
    this.strip?.geometry.dispose(); this.stripMat?.dispose();
  }
}

// ———————————————————————————————————————————————————————————————————————————————————————————————— environment

/**
 * The floor: a large dark plane with a fine grid that fades with distance from `centre`, plus a soft accent pool under
 * the subject. It writes depth (the DoF blurs it where it lies).
 */
export class Floor {
  readonly mesh: THREE.Mesh;
  readonly mat: THREE.ShaderMaterial;
  constructor(o: { y?: number; size?: number; cell?: number; centre?: [number, number]; reach?: number; grid?: number; pool?: PaletteKey | `#${string}`; poolK?: number } = {}) {
    const size = o.size ?? 60;
    this.mat = new THREE.ShaderMaterial({
      toneMapped: false,
      uniforms: {
        uBase: { value: hdr('bg', 1.6) },
        uVoid: { value: hdr('#0A0706', 1) },
        uLine: { value: hdr('fg', 1) },
        uPool: { value: hdr(o.pool ?? 'accent', 1) },
        uPoolK: { value: o.poolK ?? 0.12 },
        uGrid: { value: o.grid ?? 0.05 },
        uCell: { value: o.cell ?? 0.5 },
        uC: { value: new THREE.Vector2(...(o.centre ?? [0, 0])) },
        uReach: { value: o.reach ?? 6 },
        uShift: { value: new THREE.Vector2(0, 0) },
      },
      vertexShader: /* glsl */ `
        varying vec2 vXZ;
        void main() { vec4 w = modelMatrix * vec4(position, 1.0); vXZ = w.xz; gl_Position = projectionMatrix * viewMatrix * w; }`,
      fragmentShader: /* glsl */ `
        uniform vec3 uBase, uVoid, uLine, uPool; uniform float uPoolK, uGrid, uCell, uReach; uniform vec2 uC, uShift;
        varying vec2 vXZ;
        void main() {
          vec2 p = (vXZ + uShift) / uCell;
          vec2 g = abs(fract(p - 0.5) - 0.5) / fwidth(p);
          float line = 1.0 - min(min(g.x, g.y), 1.0);
          float d = length(vXZ - uC);
          float fade = exp(-d * d / (uReach * uReach));
          float pool = exp(-d * d / (0.35 * uReach * uReach));
          vec3 c = mix(uVoid, uBase, fade) + uLine * line * uGrid * fade + uPool * uPoolK * pool;
          gl_FragColor = vec4(c, 1.0);
        }`,
      extensions: { derivatives: true } as never,
    });
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry(size, size), this.mat);
    this.mesh.rotation.x = -Math.PI / 2;
    this.mesh.position.y = o.y ?? -1;
  }
  /** Slide the grid (a sense of travel) by (dx, dz) world units. */
  shift(dx: number, dz: number) { this.mat.uniforms.uShift!.value.set(dx, dz); }
  dispose() { this.mesh.geometry.dispose(); this.mat.dispose(); }
}

/** The haze: a big soft radial glow far behind the subject (the volumetric back light), in `role` at `k`. */
export class Haze {
  readonly mesh: THREE.Mesh;
  readonly mat: THREE.ShaderMaterial;
  constructor(o: { z?: number; y?: number; size?: number; role?: PaletteKey | `#${string}`; k?: number; role2?: PaletteKey | `#${string}`; k2?: number } = {}) {
    this.mat = new THREE.ShaderMaterial({
      toneMapped: false,
      uniforms: {
        uA: { value: hdr(o.role ?? '#22160f', o.k ?? 1) },
        uB: { value: hdr(o.role2 ?? 'accentDim', o.k2 ?? 0.08) },
        uVoid: { value: hdr('#0A0706', 1) },
        uT: { value: 0 },
      },
      vertexShader: /* glsl */ `varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
      fragmentShader: /* glsl */ `
        uniform vec3 uA, uB, uVoid; uniform float uT; varying vec2 vUv;
        void main() {
          vec2 p = vUv - 0.5;
          float r = length(p * vec2(1.0, 1.6));
          float a = exp(-r * r * 9.0);
          float b = exp(-dot(p - vec2(0.12 * sin(uT * 0.3), -0.08), p - vec2(0.12 * sin(uT * 0.3), -0.08)) * 26.0);
          gl_FragColor = vec4(uVoid + uA * a + uB * b, 1.0);
        }`,
    });
    const s = o.size ?? 40;
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry(s * 1.78, s), this.mat);
    this.mesh.position.set(0, o.y ?? 0, o.z ?? -12);
  }
  /** Keep it facing the camera and breathing. */
  pose(t: number, cam: THREE.Camera) { this.mat.uniforms.uT!.value = t; this.mesh.quaternion.copy(cam.quaternion); }
  dispose() { this.mesh.geometry.dispose(); this.mat.dispose(); }
}

/**
 * Dust: soft motes in a box round the subject, drifting slowly, in warm white and a little accent. Additive, no depth
 * write: near ones read as big soft bokeh discs (their size grows with nearness), far ones as specks.
 */
export class Dust {
  readonly points: THREE.Points;
  readonly mat: THREE.ShaderMaterial;
  constructor(o: { count?: number; box?: [number, number, number]; centre?: [number, number, number]; size?: number; role?: PaletteKey | `#${string}`; k?: number; seed?: number } = {}) {
    const n = o.count ?? 220, [bx, by, bz] = o.box ?? [10, 6, 10], [cx, cy, cz] = o.centre ?? [0, 0, 0];
    const rnd = mulberry32(o.seed ?? 11);
    const pos = new Float32Array(n * 3), ph = new Float32Array(n), warm = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      pos[i * 3] = cx + (rnd() - 0.5) * bx; pos[i * 3 + 1] = cy + (rnd() - 0.5) * by; pos[i * 3 + 2] = cz + (rnd() - 0.5) * bz;
      ph[i] = rnd() * 100; warm[i] = rnd();
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geo.setAttribute('aPh', new THREE.BufferAttribute(ph, 1));
    geo.setAttribute('aWarm', new THREE.BufferAttribute(warm, 1));
    this.mat = new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false,
      uniforms: {
        uT: { value: 0 }, uSize: { value: o.size ?? 0.03 }, uPx: { value: 1080 },
        uA: { value: hdr('#FFE2C4', o.k ?? 0.5) }, uB: { value: hdr(o.role ?? 'accent', (o.k ?? 0.5) * 1.6) },
      },
      vertexShader: /* glsl */ `
        uniform float uT, uSize, uPx; attribute float aPh; attribute float aWarm; varying float vW; varying float vA;
        void main() {
          vec3 p = position + vec3(sin(uT * 0.13 + aPh) * 0.25, sin(uT * 0.11 + aPh * 1.7) * 0.18 + uT * 0.02, cos(uT * 0.09 + aPh) * 0.25);
          vec4 mv = modelViewMatrix * vec4(p, 1.0);
          float d = max(0.2, -mv.z);
          gl_PointSize = clamp(uSize * uPx / d * (1.0 + 2.5 / d), 1.0, 90.0);
          vW = aWarm; vA = (0.35 + 0.65 * sin(uT * 0.7 + aPh) * 0.5 + 0.5) / (1.0 + 0.15 * gl_PointSize);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: /* glsl */ `
        uniform vec3 uA, uB; varying float vW; varying float vA;
        void main() {
          float r = length(gl_PointCoord - 0.5) * 2.0;
          float a = smoothstep(1.0, 0.75, r) * (0.6 + 0.4 * smoothstep(0.2, 0.95, r));
          gl_FragColor = vec4((vW > 0.85 ? uB : uA) * a * vA, 1.0);
        }`,
    });
    this.points = new THREE.Points(geo, this.mat);
    this.points.frustumCulled = false;
  }
  pose(t: number) { this.mat.uniforms.uT!.value = t; }
  dispose() { this.points.geometry.dispose(); this.mat.dispose(); }
}

export { LIN };
