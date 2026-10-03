// The machine's page of scene `anywhere` (Plan 2 Task 24), and the two pages' headlines.
//
// - The chips under the terminal: `one static binary` `no CGo` `arm64 + amd64` (the facts sheet's line, split at its
//   dots). repo's solid tiles (repo-chips.ts chipGeometry: satin panel2 under a clear coat, the name in flat mono bone),
//   dealt out of the machine: each starts hidden behind the terminal (an opaque panel), slides down out from under its
//   bottom edge on a tight spring that lands on its sixteenth, tipped back and righting, and a light glints across the
//   row as the last lands. A spec list, spread over the height four chips would take so the page keeps its weight.
// - The headlines: her words over each page, "On your machine…" and "or in my cloud.", one kerned line each, its hero
//   word extruded satin bone that slams in from depth on her onset (her's headline), the rest flat Bricolage that types
//   in word by word as she says it, glyph by glyph on the output frame grid.
import * as THREE from 'three';
import { Type3D, type Glyph3D } from '../engine/type3d';
import { slam } from '../engine/motion';
import { FPS, frameIdx } from '../engine/util';

/** Flat type: a sliver of depth (em), no bevel. */
export const FLAT = { depth: 0.002, bevel: 0 } as const;

// ------------------------------------------------------------------------------------------------ the chips

/** The chips: height, padding round the name, the gap between chips and between rows, corner, depth, bevel, the
 * name's em, and the stack's height as a column (four chips' worth at the row gap). Panel px. */
export const CHIP = { h: 46, pad: 16, gap: 14, row: 12, r: 13, depth: 12, bevel: 3, em: 22, stack: 4 * 46 + 3 * 12 } as const;

/** The row gap that spreads `n` chips in a column over the stack's height. */
export const stackGap = (n: number) => (n > 1 ? (CHIP.stack - n * CHIP.h) / (n - 1) : CHIP.row);

export interface ChipPlace {
  name: string;
  /** Left edge and top (px in the page, y down), width. */
  x: number;
  y: number;
  w: number;
}

/** The chip names: the facts sheet's line split at its dots. */
export const chipNames = (line: string) => line.split(' · ');

/**
 * Lay the chips out in rows from (x0, y0), wrapping before `maxW` (1: one a row, a column), `row` px between rows:
 * each as wide as its name in mono cells plus padding.
 */
export function layoutChipRows(names: readonly string[], x0: number, y0: number, maxW: number, row: number = CHIP.row): ChipPlace[] {
  const adv = 0.6 * CHIP.em, out: ChipPlace[] = [];
  let x = x0, y = y0;
  names.forEach((name) => {
    const w = Array.from(name).length * adv + 2 * CHIP.pad;
    if (x > x0 && x + w > x0 + maxW) (x = x0), (y += CHIP.h + row);
    out.push({ name, x, y, w });
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
