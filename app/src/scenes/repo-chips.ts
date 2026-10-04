// The `ls` chips for `repo` (Plan 2 Task 14): the listing `facts/  incidents/  rules/  skills/` pops out of the
// terminal's output row as four chips with weight.
//
// A chip is a solid tile, not a sticker: a rounded rectangle with depth and a round bevel on both faces (chipGeometry,
// its normals exact: the face flat, the bevel turning smoothly onto the wall), in dark satin panel2 under a clear coat
// that takes the studio's highlights on its bevel, with its name in flat mono bone on the face. Each pops on a 32nd
// note after the one before: it launches from inside the panel's face, tipped back and a little small, rises toward
// the camera on a heavy spring that lands on its beat and overshoots a hair, and rights itself a moment after (follow-
// through); its soft shadow on the panel grows and softens as it lifts; the panel takes the kick of each launch.
// (chipPop and recoil are pure functions of t.)
import * as THREE from 'three';
import { slam } from '../engine/motion';

/** A chip in the row, in panel px: its name, left edge and width. */
export interface ChipSpec {
  name: string;
  x: number;
  w: number;
}

/**
 * Lay the names out from x0 along the row: each chip as wide as its name in mono cells (`adv` px each) plus `pad` either
 * side, `gap` between chips.
 */
export function layoutChips(names: readonly string[], x0: number, adv: number, pad: number, gap: number): ChipSpec[] {
  let x = x0;
  return names.map((name) => {
    const w = Array.from(name).length * adv + 2 * pad;
    const c = { name, x, w };
    x += w + gap;
    return c;
  });
}

/** The pop's springs: the lift (heavy, a 7% overshoot) and the righting (a little slower: it follows through). */
export const POP = {
  lift: { freq: 4.6, damping: 0.64 },
  right: { freq: 4.0, damping: 0.66 },
  /** Tipped back at launch (radians about the chip's x), and its scale then. */
  tilt: 0.85,
  scale: 0.8,
} as const;

export interface Pop {
  /** Launched (and drawn). */
  on: boolean;
  /** 0 in the panel's face, 1 at its height, past 1 in the overshoot. */
  lift: number;
  scale: number;
  /** Radians about the chip's x axis: tipped back, righting to 0. */
  tilt: number;
}

/** A chip's pop at t, landing (its lift first reaching 1) at `land`. */
export function chipPop(t: number, land: number): Pop {
  const lift = slam(t, land, POP.lift);
  const right = slam(t, land + 0.03, POP.right);
  return {
    on: lift > 0,
    lift,
    scale: POP.scale + (1 - POP.scale) * Math.min(1, lift),
    tilt: POP.tilt * (1 - right),
  };
}

/**
 * How long before its landing a chip launches: the lift spring's rise time (motion.ts slam's default lead, when an
 * under-damped spring first reaches 1).
 */
export const LAUNCH = (Math.PI / 2 + Math.asin(POP.lift.damping)) / (2 * Math.PI * POP.lift.freq * Math.sqrt(1 - POP.lift.damping ** 2));

/**
 * The panel's recoil from the chips landing at `lands` (s): pushed back as each launches, ringing out in about 0.2 s. A
 * fraction of the chip's lift (0 at rest; positive is away from the camera).
 */
export function recoil(t: number, lands: readonly number[]): number {
  let r = 0;
  for (const at of lands) {
    const dt = t - (at - LAUNCH);
    if (dt <= 0) continue;
    r += 0.06 * Math.exp(-dt * 16) * Math.sin(dt * 2 * Math.PI * 7);
  }
  return r;
}

/**
 * A chip: a w × h rounded rectangle (corner radius r) `depth` thick, its face at z = 0 and its back at −depth, the edge
 * of each face rounded by a quarter circle of radius `bevel`. Centred on the origin in x and y. Exact smooth normals: the
 * face's are +z to its edge, where the bevel takes over.
 */
export function chipGeometry(w: number, h: number, r: number, depth: number, bevel: number, cornerSegs = 10, bevelSegs = 6): THREE.BufferGeometry {
  r = Math.min(r, w / 2, h / 2);
  bevel = Math.min(bevel, r, depth / 2);
  // the outline: four quarter circles, counter-clockwise from the right edge; the straight edges join them
  const ring: { c: [number, number]; n: [number, number] }[] = [];
  const corners: [number, number, number][] = [[w / 2 - r, h / 2 - r, 0], [-w / 2 + r, h / 2 - r, 0.5], [-w / 2 + r, -h / 2 + r, 1], [w / 2 - r, -h / 2 + r, 1.5]];
  for (const [cx, cy, a0] of corners) {
    for (let k = 0; k <= cornerSegs; k++) {
      const a = Math.PI * (a0 + k / (2 * cornerSegs));
      ring.push({ c: [cx, cy], n: [Math.cos(a), Math.sin(a)] });
    }
  }
  // the profile round the edge: (inset from the outline, z, the normal's share along the outline's normal, along z)
  const prof: [number, number, number, number][] = [];
  for (let k = 0; k <= bevelSegs; k++) {
    const a = (Math.PI / 2) * (k / bevelSegs); // the face's edge (normal +z) round to the wall (normal outward)
    prof.push([bevel * (1 - Math.sin(a)), -bevel * (1 - Math.cos(a)), Math.sin(a), Math.cos(a)]);
  }
  for (let k = 0; k <= bevelSegs; k++) {
    const a = (Math.PI / 2) * (k / bevelSegs); // the wall round to the back's edge
    prof.push([bevel * (1 - Math.cos(a)), -(depth - bevel) - bevel * Math.sin(a), Math.cos(a), -Math.sin(a)]);
  }
  const pos: number[] = [], nor: number[] = [], idx: number[] = [];
  for (const p of ring) {
    for (const [inset, z, nr, nz] of prof) {
      const rr = r - inset;
      pos.push(p.c[0] + rr * p.n[0], p.c[1] + rr * p.n[1], z);
      nor.push(nr * p.n[0], nr * p.n[1], nz);
    }
  }
  const P = ring.length, J = prof.length;
  for (let i = 0; i < P; i++) {
    const i2 = (i + 1) % P;
    for (let j = 0; j < J - 1; j++) {
      const a = i * J + j, b = i2 * J + j, c = i2 * J + j + 1, d = i * J + j + 1;
      idx.push(a, d, b, b, d, c);
    }
  }
  // the face and the back: fans from the centre to the bevel's inner edge (the outline inset by the bevel; convex)
  const cap = (j: number, z: number, nz: number) => {
    const c0 = pos.length / 3;
    pos.push(0, 0, z);
    nor.push(0, 0, nz);
    for (let i = 0; i < P; i++) {
      pos.push(pos[3 * (i * J + j)]!, pos[3 * (i * J + j) + 1]!, z);
      nor.push(0, 0, nz);
    }
    for (let i = 0; i < P; i++) {
      const a = c0 + 1 + i, b = c0 + 1 + ((i + 1) % P);
      if (nz > 0) idx.push(c0, a, b);
      else idx.push(c0, b, a);
    }
  };
  cap(0, 0, 1);
  cap(J - 1, -depth, -1);
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
  geo.setIndex(idx);
  return geo;
}

/** A soft shadow under a chip: a rounded rectangle's darkness, blurred by `uBlur` px, on a quad padded to hold it. */
export class ChipShadow {
  mesh: THREE.Mesh;
  readonly u: { uSize: THREE.IUniform<THREE.Vector2>; uRadius: THREE.IUniform<number>; uBlur: THREE.IUniform<number>; uOpacity: THREE.IUniform<number>; uPad: THREE.IUniform<number> };

  /** w, h, r in panel px; `pad` px of room round it for the blur; `pxToWorld` world units per panel px. */
  constructor(w: number, h: number, r: number, pad: number, pxToWorld: number) {
    this.u = {
      uSize: { value: new THREE.Vector2(w, h) }, uRadius: { value: r }, uBlur: { value: 6 }, uOpacity: { value: 0 }, uPad: { value: pad },
    };
    const mat = new THREE.ShaderMaterial({
      uniforms: this.u,
      vertexShader: /* glsl */ `
        uniform vec2 uSize; uniform float uPad; varying vec2 vPx;
        void main() { vPx = (uv - 0.5) * (uSize + 2.0 * uPad); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
      fragmentShader: /* glsl */ `
        uniform vec2 uSize; uniform float uRadius, uBlur, uOpacity; varying vec2 vPx;
        void main() {
          vec2 q = abs(vPx) - 0.5 * uSize + uRadius;
          float d = length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - uRadius;
          float a = 1.0 - smoothstep(-0.5 * uBlur, uBlur, d);
          gl_FragColor = vec4(0.0, 0.0, 0.0, a * a * uOpacity);
        }`,
      transparent: true,
      depthWrite: false,
    });
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry((w + 2 * pad) * pxToWorld, (h + 2 * pad) * pxToWorld), mat);
  }

  dispose() {
    this.mesh.geometry.dispose();
    (this.mesh.material as THREE.Material).dispose();
  }
}
