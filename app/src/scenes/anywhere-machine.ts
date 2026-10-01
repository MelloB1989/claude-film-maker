// The machine's page of scene `anywhere` (Plan 2 Task 24), and the two pages' headlines.
//
// - The chips under the terminal: `one static binary` `no CGo` `arm64 + amd64` `licence verified offline` (the facts
//   sheet's line, split at its dots). repo's solid tiles (repo-chips.ts chipGeometry: satin panel2 under a clear coat,
//   the name in flat mono bone), dealt out of the machine: each starts hidden behind the terminal (an opaque panel),
//   slides down out from under its bottom edge on a tight spring that lands on its sixteenth, tipped back and righting,
//   and a light glints across the row as the last lands. The licence chip carries a ✔ drawn on in moss as it lands:
//   verified (the panels' check mark, by a pen: connect's ✔ Connected).
// - The headlines: her words over each page, "On your machine…" and "or in my cloud.", one kerned line each, its hero
//   word extruded satin bone that slams in from depth on her onset (her's headline), the rest flat Bricolage that types
//   in word by word as she says it, glyph by glyph on the output frame grid.
import * as THREE from 'three';
import { Type3D, type Glyph3D } from '../engine/type3d';
import { slam } from '../engine/motion';
import { glow } from '../engine/look';
import { FPS, frameIdx, prog } from '../engine/util';

/** Flat type: a sliver of depth (em), no bevel. */
export const FLAT = { depth: 0.002, bevel: 0 } as const;

// ------------------------------------------------------------------------------------------------ the chips

/** The chips: height, padding round the name, the gap between chips and rows, corner, depth, bevel, the name's em,
 * and the ✔'s cell (em wide) before the licence chip's name. Panel px. */
export const CHIP = { h: 46, pad: 16, gap: 14, r: 13, depth: 12, bevel: 3, em: 22, check: 1.15 } as const;

export interface ChipPlace {
  name: string;
  /** Left edge and top (px in the page, y down), width. */
  x: number;
  y: number;
  w: number;
  /** Whether it carries the ✔. */
  check: boolean;
}

/** The chip names: the facts sheet's line split at its dots. */
export const chipNames = (line: string) => line.split(' · ');

/**
 * Lay the chips out in rows from (x0, y0), wrapping before `maxW`: each as wide as its name in mono cells plus padding
 * (and the ✔'s cell on the licence chip).
 */
export function layoutChipRows(names: readonly string[], x0: number, y0: number, maxW: number): ChipPlace[] {
  const adv = 0.6 * CHIP.em, out: ChipPlace[] = [];
  let x = x0, y = y0;
  names.forEach((name, i) => {
    const check = i === names.length - 1;
    const w = Array.from(name).length * adv + 2 * CHIP.pad + (check ? CHIP.check * CHIP.em : 0);
    if (x > x0 && x + w > x0 + maxW) (x = x0), (y += CHIP.h + CHIP.gap);
    out.push({ name, x, y, w, check });
    x += w + CHIP.gap;
  });
  return out;
}

/** The deal's spring (heavy and tight: a hair of overshoot, a click), the tip at launch (radians), its scale then. */
export const DEAL = { freq: 5.2, damping: 0.68, tilt: 0.7, scale: 0.92 } as const;

/**
 * A chip's deal at t, landing on `land`: `s` its spring (0 behind the terminal, 1 home; past 1 in the overshoot),
 * `tilt` (tipped back, righting a moment after), `scale`.
 */
export function dealAt(t: number, land: number) {
  const s = slam(t, land, DEAL);
  const right = slam(t, land + 0.035, { freq: 4.4, damping: 0.66 });
  return { on: s > 0, s, tilt: DEAL.tilt * (1 - right), scale: DEAL.scale + (1 - DEAL.scale) * Math.min(1, s) };
}

// ------------------------------------------------------------------------------------------------ the ✔

/** The panels' check mark in em from its cell's left end of the baseline, y up (engine/panels.ts CHECK_PTS, CHECK_W). */
export const CHECK = { pts: [[0.05, 0.37], [0.225, 0.075], [0.565, 0.7]] as const, w: 0.12 };
/** How long the pen takes (s): it lands with the chip. */
export const PEN = 0.16;

const UV_VERT = /* glsl */ `varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;
const v2 = (p: readonly [number, number]) => `vec2(${p[0].toFixed(4)}, ${p[1].toFixed(4)})`;

/**
 * The ✔ on a chip's face, drawn on by a pen: a plane `2·half` em square round the check, its cell's left end of the
 * baseline at the plane's (cx, cy) em offset; premultiplied, its stroke covering the face and its light added.
 */
export class Check {
  mesh: THREE.Mesh;
  private u: Record<string, THREE.IUniform>;

  /** `em`: px per em; the cell's left end of the baseline at (x, y) in the parent's px (y up), z px off the face. */
  constructor(em: number, x: number, y: number, z: number) {
    const half = 1.1, mid = { x: 0.3, y: 0.38 };
    const { pts, w } = CHECK;
    this.u = { uDraw: { value: 0 }, uLevel: { value: 0 }, uHeat: { value: 0 }, uColor: { value: new THREE.Vector3(...glow('moss', 1)) } };
    const frag = /* glsl */ `
      uniform float uDraw, uLevel, uHeat;
      uniform vec3 uColor;
      varying vec2 vUv;
      float sdSeg(vec2 p, vec2 a, vec2 b) {
        vec2 pa = p - a, ba = b - a;
        return length(pa - ba * clamp(dot(pa, ba) / max(dot(ba, ba), 1e-9), 0.0, 1.0));
      }
      void main() {
        const vec2 P0 = ${v2(pts[0])}, P1 = ${v2(pts[1])}, P2 = ${v2(pts[2])};
        vec2 q = (vUv - 0.5) * ${(2 * half).toFixed(3)} + vec2(${mid.x.toFixed(3)}, ${mid.y.toFixed(3)});
        float l0 = length(P1 - P0), l1 = length(P2 - P1), s = uDraw * (l0 + l1);
        vec2 head = s <= l0 ? mix(P0, P1, s / l0) : mix(P1, P2, (s - l0) / l1);
        float d = min(sdSeg(q, P0, s <= l0 ? head : P1), s > l0 ? sdSeg(q, P1, head) : 1e3);
        float on = step(1e-5, uDraw);
        float e = d - ${(w / 2).toFixed(4)};
        float c = clamp(0.5 - e / max(fwidth(e), 1e-5), 0.0, 1.0) * on;
        vec2 hd = (q - head) / 0.09;
        float hot = uHeat * exp(-dot(hd, hd)) * on;
        gl_FragColor = vec4(uColor * (uLevel * c + 3.0 * hot), c);
      }`;
    const m = new THREE.ShaderMaterial({ uniforms: this.u, vertexShader: UV_VERT, fragmentShader: frag, transparent: true, depthWrite: false });
    m.blending = THREE.CustomBlending;
    m.blendEquation = THREE.AddEquation;
    m.blendSrc = THREE.OneFactor;
    m.blendDst = THREE.OneMinusSrcAlphaFactor;
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry(2 * half * em, 2 * half * em), m);
    this.mesh.position.set(x + mid.x * em, y + mid.y * em, z);
    this.mesh.renderOrder = 3;
  }

  /** How far the pen is (0..1), the stroke's light (a glow() level; 0.42 is flat moss), the pen's head's heat. */
  set(draw: number, level: number, heat: number) {
    this.mesh.visible = draw > 0;
    this.u.uDraw!.value = Math.min(1, Math.max(0, draw));
    this.u.uLevel!.value = level;
    this.u.uHeat!.value = heat;
  }

  dispose() {
    this.mesh.geometry.dispose();
    (this.mesh.material as THREE.Material).dispose();
  }
}

/** The pen along the ✔ at t, landing at `land`: it sets down, runs the short arm, flicks up the long one. */
export function penAt(t: number, land: number) {
  const u = prog(t, land - PEN, land);
  return 0.3 * u + 0.7 * u * u;
}

// ------------------------------------------------------------------------------------------------ the headlines

/**
 * A headline: one kerned line set twice from the same layout (Type3D), extruded and flat, each glyph shown from one of
 * the two, so the hero word and the flat words sit on one baseline with the line's own spacing (her's DiffLine,
 * without a gutter mark). The group's origin is the text origin (left end, baseline).
 */
export class Headline {
  group = new THREE.Group();
  solid: Type3D;
  flat: Type3D;
  readonly hero: number;
  /** Each word's glyphs, from the copy that shows it. */
  readonly words: Glyph3D[][] = [];

  constructor(text: string, family: string, size: number, hero: number, heroMat: THREE.Material, flatMat: THREE.Material) {
    this.hero = hero;
    this.solid = new Type3D(text, { family, size }, heroMat);
    this.flat = new Type3D(text, { family, size, ...FLAT }, flatMat);
    for (const g of this.solid.glyphs) g.mesh.visible = g.word === hero;
    for (const g of this.flat.glyphs) g.mesh.visible = g.word !== hero;
    this.group.add(this.solid.group, this.flat.group);
    const n = Math.max(0, ...this.solid.glyphs.map((g) => g.word)) + 1;
    for (let w = 0; w < n; w++) this.words.push((w === hero ? this.solid : this.flat).glyphs.filter((g) => g.word === w));
  }

  /** Left and right ends of word `w` (line space x). */
  span(w: number): [number, number] {
    const gs = this.words[w]!;
    return [gs[0]!.x, gs[gs.length - 1]!.x + gs[gs.length - 1]!.w];
  }

  /**
   * Pose the line at t: flat word w types in glyph by glyph from `at[w]` (one glyph a frame, on the output frame grid);
   * the hero word slams in from depth on its onset, glyph by glyph a hair apart.
   */
  pose(t: number, at: readonly number[]) {
    const tq = frameIdx(t) / FPS, size = this.solid.size;
    this.words.forEach((gs, w) => {
      const t0 = at[w] ?? Infinity;
      gs.forEach((g, k) => {
        const m = g.mesh;
        if (w !== this.hero) {
          m.visible = tq >= t0 + k / FPS - 1e-6;
          return;
        }
        const s = slam(t, t0 + 0.016 * k);
        m.visible = s > 0;
        m.position.copy(g.home);
        m.position.z += (s - 1) * 3.2 * size;
        m.rotation.set((1 - s) * 0.6, 0, 0);
        m.scale.setScalar(size);
      });
    });
  }

  dispose() {
    this.solid.dispose();
    this.flat.dispose();
  }
}
