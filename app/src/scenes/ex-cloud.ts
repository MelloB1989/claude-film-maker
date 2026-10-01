// The float cloud of scene `ex`, as data: about six thousand float numerals in a jittered lattice (rows, columns and
// layers, precise rather than a nebula) filling a thick shell of a loose spheroid, the Maya region the two cards write
// to, its overwrite, and where every numeral falls when the store collapses. Pure and seeded (no DOM, no GL), so bun tests it
// and every frame is the same in any order.
//
// A numeral is seven mono cells, as an array prints its floats: a sign cell (− or blank) then d.dddd, so the columns
// line up. Its text without the blank is a float numeral of the facts sheet (§11.10: `0.2143`, `−0.0931`).
import { hash } from '../engine/util';

/** World units (m) per em of the cloud's numerals, and a cell's advance (JetBrains Mono: 600 of 1000 units). */
export const EM = 0.0075;
export const ADV = 0.6 * EM;
/** Cells per numeral: a sign (− or a blank), then d.dddd. */
export const CELLS = 7;
/** Lattice pitch (m): a column is a numeral and two blank cells; rows are 2.1 em; layers are deeper apart. */
export const PITCH = { x: 9 * ADV, y: 2.1 * EM, z: 0.0545 } as const;
/** The spheroid's semi-axes (m): wider than tall, as deep as tall. */
export const SPHEROID = { rx: 0.56, ry: 0.36, rz: 0.36 } as const;
/**
 * The lattice fills a thick shell of the spheroid (from SHELL of its radius out) and only a seeded few of the points
 * inside it (CORE): from the front the near face reads crisp and ordered over a soft echo of the far one, where a full
 * volume read as a haze of a dozen layers; seen edge-on at the rim the shell gathers into a brighter limb.
 */
const SHELL = 0.68;
const CORE = 0.08;
/** How far each numeral strays from its lattice point (fractions of a pitch): orderly, not a nebula. */
const JITTER = { x: 0.06, y: 0.08, z: 0.18 } as const;
/** The spheroid's edge is loose: each numeral's own boundary is the unit spheroid pushed in or out by up to this. */
const EDGE = 0.07;

export const MINUS = '−';

/** A float as the cloud prints it: seven cells, a sign (− or a blank) then d.dddd. |v| stays below 1. */
export function cells(v: number): string {
  const a = Math.min(Math.max(Math.abs(v), 0.0001), 0.9999);
  return (v < 0 ? MINUS : ' ') + a.toFixed(4);
}

/** The numeral as it reads (no leading blank): the facts sheet's float shape. */
export const shown = (v: number) => cells(v).trimStart();

/** A seeded float with an embedding's spread: mostly small, a few large, either sign; four places. */
export function floatOf(seed: number): number {
  const u = hash(seed, 1), m = hash(seed, 2), s = hash(seed, 3);
  const mag = u < 0.62 ? 0.0012 + 0.098 * m : 0.1 + 0.86 * m * m;
  return (s < 0.5 ? -1 : 1) * Math.max(1, Math.round(mag * 1e4)) / 1e4;
}

export interface Numeral {
  /** Index in the cloud (the order glyphs are drawn: far layers first). */
  id: number;
  /** Lattice indices: column, row, layer (+k is toward the front, +z). */
  i: number;
  j: number;
  k: number;
  /** The left end of its sign cell, on the baseline (m). */
  x: number;
  y: number;
  z: number;
  /** Its float and its seven cells. */
  v: number;
  text: string;
  /** Its strength: 0.25–0.6 of the way from ink to bone (spec §4 02). */
  bright: number;
  /** Ellipsoidal radius of its centre (0 at the middle, about 1 at the edge). */
  rn: number;
  seed: number;
  /** The Maya region: -1 outside it; else its row (0..2 from the top, 1 the centre row) and slot (0..4, left to right). */
  regionRow: number;
  slot: number;
}

/** The Maya region: the front of the cloud a little left of and above its middle, five numerals by three rows. */
export const REGION = { cols: 5, rows: 3, at: { x: -0.085, y: 0.05 } } as const;
/** The centre row's slots the Berlin card's three floats land in (the other two hold numerals of their own). */
export const BERLIN_SLOTS = [1, 2, 3] as const;

export interface Cloud {
  numerals: Numeral[];
  /** The region's numerals: [row 0..2 from the top][slot 0..4]; row 1 is the centre row. */
  region: Numeral[][];
  /** The lattice point of the region's centre (column, row, layer). */
  centre: { i: number; j: number; k: number };
  /** The three numerals of the spec (0.2143, −0.0931, 0.7715), in the row above the region. */
  named: Numeral[];
}

/**
 * Each layer's grid is offset from the others' by a seeded fraction of a pitch, so a layer is a precise grid but the
 * layers interleave: no row or column of one hides behind another's. (A regular sequence of offsets, golden-ratio steps,
 * still lines the layers up somewhere on screen, where perspective cancels its steps: a moiré cross.)
 */
const layerShift = (k: number) => ({ x: hash(k, 501), y: hash(k, 502) });
/** Where a lattice point is (m): its numeral's centre. Region numerals sit exactly on the lattice. */
const at = (i: number, j: number, k: number) => {
  const sh = layerShift(k);
  return { x: (i + sh.x - 0.5) * PITCH.x, y: (j + sh.y - 0.5) * PITCH.y, z: k * PITCH.z };
};

/**
 * The cloud: every lattice point whose jittered centre falls inside its loosened spheroid, plus the Maya region (an
 * exact 5x3 block in the front layer, with nothing in front of it) and the spec's three numerals above it. Sorted far
 * layer first (the camera looks along −z), so the instanced draw blends back to front.
 */
export function buildCloud(named: readonly number[]): Cloud {
  const { rx, ry, rz } = SPHEROID;
  const ni = Math.ceil(rx / PITCH.x) + 1, nj = Math.ceil(ry / PITCH.y) + 1, nk = Math.ceil(rz / PITCH.z) + 1;
  // the region's lattice point: the front-most layer at its spot
  const ci = Math.round(REGION.at.x / PITCH.x), cj = Math.round(REGION.at.y / PITCH.y);
  const p0 = at(ci, cj, 0);
  const front = rz * Math.sqrt(Math.max(0, 1 - (p0.x / rx) ** 2 - (p0.y / ry) ** 2));
  const ck = Math.floor(front / PITCH.z);
  const half = { i: (REGION.cols - 1) / 2, j: (REGION.rows - 1) / 2 };
  // the window kept clear around the region and in front of it, and the named numerals' row above it
  const inWindow = (i: number, j: number, k: number) => Math.abs(i - ci) <= half.i + 1 && Math.abs(j - cj) <= half.j + 2 && k >= ck;
  const raw: Omit<Numeral, 'id'>[] = [];
  const seedOf = (i: number, j: number, k: number) => (k + 97) * 1_000_003 + (j + 97) * 1009 + (i + 97);
  const make = (i: number, j: number, k: number, exact: boolean, v?: number): Omit<Numeral, 'id'> => {
    const seed = seedOf(i, j, k);
    const c = at(i, j, k);
    if (!exact) {
      c.x += (hash(seed, 11) - 0.5) * 2 * JITTER.x * PITCH.x;
      c.y += (hash(seed, 12) - 0.5) * 2 * JITTER.y * PITCH.y;
      c.z += (hash(seed, 13) - 0.5) * 2 * JITTER.z * PITCH.z;
    }
    const value = v ?? floatOf(seed);
    return {
      i, j, k, x: c.x - (CELLS / 2) * ADV, y: c.y - 0.365 * EM, z: c.z, v: value, text: cells(value),
      bright: 0.25 + 0.35 * hash(seed, 21) ** 2.2, rn: Math.hypot(c.x / rx, c.y / ry, c.z / rz), seed, regionRow: -1, slot: -1,
    };
  };
  for (let k = -nk; k <= nk; k++) {
    for (let j = -nj; j <= nj; j++) {
      for (let i = -ni; i <= ni; i++) {
        if (inWindow(i, j, k)) continue;
        const n = make(i, j, k, false);
        if (n.rn > 1 + EDGE * (2 * hash(n.seed, 17) - 1)) continue;
        if (n.rn < SHELL + EDGE * (2 * hash(n.seed, 18) - 1) && hash(n.seed, 19) >= CORE) continue;
        raw.push(n);
      }
    }
  }
  // the region, exact, and the named numerals in the row above it
  const region: Omit<Numeral, 'id'>[][] = [];
  for (let r = 0; r < REGION.rows; r++) {
    const row: Omit<Numeral, 'id'>[] = [];
    for (let s = 0; s < REGION.cols; s++) {
      const n = make(ci - half.i + s, cj + half.j - r, ck, true);
      n.regionRow = r;
      n.slot = s;
      row.push(n);
      raw.push(n);
    }
    region.push(row);
  }
  const namedRaw = named.map((v, s) => {
    const n = make(ci - 1 + s, cj + half.j + 2, ck, true, v);
    raw.push(n);
    return n;
  });
  // far layers first; within a layer, top to bottom and left to right
  raw.sort((a, b) => a.z - b.z || b.y - a.y || a.x - b.x);
  const numerals = raw.map((n, id) => Object.assign(n, { id }) as Numeral);
  return {
    numerals,
    region: region as Numeral[][],
    centre: { i: ci, j: cj, k: ck },
    named: namedRaw as Numeral[],
  };
}

// ------------------------------------------------------------------------------------------------ the cards

/** The floats a sentence becomes: one seven-cell numeral per seven characters (Berlin: 21 → 3, Lisbon: 35 → 5). */
export function cardFloats(sentence: string, seed: number): number[] {
  const n = Math.ceil(Array.from(sentence).length / CELLS);
  return Array.from({ length: n }, (_, k) => floatOf(seed * 7919 + k * 104729));
}

/** The cells a sentence's characters morph into: its floats' cells end to end, cut to the sentence's length. */
export const morphTargets = (sentence: string, floats: readonly number[]) =>
  Array.from(floats.map(cells).join('')).slice(0, Array.from(sentence).length);

// ------------------------------------------------------------------------------------------------ the collapse

/** How each numeral falls into the line: its slot on the line (0..1 across it) and its delay after the drop (s). */
export function fallOf(n: Numeral): { slot: number; delay: number } {
  const u = (n.x + (CELLS / 2) * ADV + SPHEROID.rx) / (2 * SPHEROID.rx);
  return { slot: Math.min(1, Math.max(0, u + 0.02 * (hash(n.seed, 31) - 0.5))), delay: 0.014 * hash(n.seed, 32) };
}

/**
 * The fall (m, s): from height h above the line under gravity g, after a delay. Returns how far it has fallen (0..1 of
 * the way) and whether it has landed; the time it takes is sqrt(2h / g).
 */
export function fall(dt: number, h: number, g: number): { k: number; landed: boolean; dur: number } {
  const dur = Math.sqrt((2 * Math.max(h, 1e-6)) / g);
  if (dt <= 0) return { k: 0, landed: false, dur };
  const y = 0.5 * g * dt * dt;
  return { k: Math.min(1, y / Math.max(h, 1e-6)), landed: y >= h, dur };
}
