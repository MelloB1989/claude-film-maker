// Kinetic 3D type: hero words as extruded, bevelled Bricolage, set exactly where the flat 2D line sets them.
//
// Outlines. opentype.js gives a glyph's contours as M/L/Q/C/Z commands in font units, y up. They are flattened to
// polylines in em (flatten: an even turn per segment, never further than FLAT from the curve), merged where they
// overlap (unionNonzero), then go through a THREE.ShapePath and toShapes, which nests each counter in its outline.
// The merge is needed because the film's static Bricolage instances keep the variable font's overlapping contours
// (fontTools' instancer leaves overlaps in): the e is one contour whose crossbar crosses its own bowl, the bars of A, E,
// F, H, T, 4, + and # run into their stems, & and @ are loops over loops. A 2D fill hides that, since the nonzero rule
// fills an overlap once; an extrusion does not: earcut fills the eye of the e, and the bevels of overlapping pieces cut
// grooves where they meet. Merged, the loops are simple and oriented, outlines counter-clockwise and counters clockwise,
// whichever way the font drew them (TrueType outlines run clockwise, CFF ones counter-clockwise).
//
// Geometry. ExtrudeGeometry with a round bevel (a quarter circle of radius `bevel`) whose walls stand on the outline
// (bevelOffset −bevel): the silhouette is the 2D glyph's and only the face is inset, so the weight and the counters
// match the flat type. Normals are rebuilt (three's are per face): faces flat, walls level, the bevel turning smoothly
// from face to wall, smooth round curves and creased at corners. Built once per (family, char, depth, bevel, segments)
// in em and shared by every Type3D using it; the last one to let go frees it.
//
// Layout. Glyph x is layout()'s kerned x (Canvas2D, the measure every 2D line in the film uses), measured at 1000 px
// and scaled to world units, so a 3D word keeps the kerning of the same word set flat. Each glyph is its own mesh,
// pivoted at its centre (mid-advance, half the x-height, mid-depth) so it can slam, tip and scale in place: `home` is
// its rest position, the face of the line lies in the group's z = 0 plane and the text origin (left end, baseline) is
// the group's origin.
//
// Materials. Mat.satinBone() is the film's type surface. Mat.accent() is the same satin with the diff glow: a line of
// blood or moss light at a glow() level along the seam where the bevel meets the wall, fading back along the wall,
// spliced into three's physical shader. The face and the inner bevel stay bone (bone never blooms), so the word reads
// as bone type lit from its edges: not a glowing word, not a neon outline, not a pastel-sided slab.
import * as THREE from 'three';
import type { PathCommand } from 'opentype.js';
import { layout, ot } from './type';
import { LIN } from './palette';
import { GLOW_LEVEL, glow } from './look';

/** Depth and bevel of hero type, in em (motion language v2: 0.16 and 0.012). */
export const DEPTH = 0.16;
export const BEVEL = 0.012;
/** Curve segments per quarter turn of a curve's tangent (7.5° a segment). */
export const CURVE_SEGMENTS = 12;
/** Segments round the bevel's quarter circle: the normals step 22.5° across it and are smoothed between. */
const BEVEL_SEGMENTS = 4;
/** A flattened curve stays within this of the true curve (em): 0.2 px at 1000 px per em. */
const FLAT = 2e-4;
/** Faces meeting at more than this are a corner (creased); less, a curve or the bevel (smoothed). */
const CREASE = (40 * Math.PI) / 180;
/** layout() measures at this size: one px per font unit of a 1000-unit em, far above Canvas2D's rounding. */
const UNIT_PX = 1000;
/** Points closer than this (em) are one point; an edge closer than this to a point runs through it. */
const EPS = 1e-9;
/** Loops smaller than this (em²) are slivers left by near-touching edges, and go. */
const MIN_AREA = 1e-8;

export type P = { x: number; y: number };

// ------------------------------------------------------------------------------------------------------- outlines

const turn = (a: P, b: P, c: P) => {
  const ux = b.x - a.x, uy = b.y - a.y, vx = c.x - b.x, vy = c.y - b.y;
  return (ux === 0 && uy === 0) || (vx === 0 && vy === 0) ? 0 : Math.abs(Math.atan2(ux * vy - uy * vx, ux * vx + uy * vy));
};
/** Segments for a curve turning `rad` whose furthest point is `dev` off its chord. */
const divisions = (rad: number, dev: number, perQuarter: number) =>
  Math.min(256, Math.max(1, Math.ceil((rad / (Math.PI / 2)) * perQuarter - 1e-9), Math.ceil(Math.sqrt(dev / FLAT) - 1e-9)));

/**
 * A glyph's commands (font units, y up) as closed polylines in em, y up, with no repeated points. A curve gets
 * `perQuarter` segments per quarter turn of its tangent, and more where it is long and flat enough to stray further than
 * FLAT from its chord.
 */
export function flatten(cmds: readonly PathCommand[], upm: number, perQuarter = CURVE_SEGMENTS): P[][] {
  const k = 1 / upm, out: P[][] = [];
  let cur: P[] = [];
  const put = (x: number, y: number) => {
    const l = cur[cur.length - 1];
    if (!l || l.x !== x || l.y !== y) cur.push({ x, y });
  };
  const close = () => {
    const f = cur[0], l = cur[cur.length - 1];
    if (cur.length > 1 && f!.x === l!.x && f!.y === l!.y) cur.pop();
    if (cur.length >= 3) out.push(cur);
    cur = [];
  };
  for (const c of cmds) {
    if (c.type === 'M') {
      close();
      put(c.x * k, c.y * k);
    } else if (c.type === 'L') put(c.x * k, c.y * k);
    else if (c.type === 'Q') {
      const p0 = cur[cur.length - 1] ?? { x: 0, y: 0 }, p1 = { x: c.x1 * k, y: c.y1 * k }, p2 = { x: c.x * k, y: c.y * k };
      const n = divisions(turn(p0, p1, p2), Math.hypot(p0.x - 2 * p1.x + p2.x, p0.y - 2 * p1.y + p2.y) / 4, perQuarter);
      for (let i = 1; i <= n; i++) {
        const t = i / n, u = 1 - t;
        put(u * u * p0.x + 2 * u * t * p1.x + t * t * p2.x, u * u * p0.y + 2 * u * t * p1.y + t * t * p2.y);
      }
    } else if (c.type === 'C') {
      const p0 = cur[cur.length - 1] ?? { x: 0, y: 0 };
      const p1 = { x: c.x1 * k, y: c.y1 * k }, p2 = { x: c.x2 * k, y: c.y2 * k }, p3 = { x: c.x * k, y: c.y * k };
      const dev = 0.75 * Math.max(Math.hypot(p0.x - 2 * p1.x + p2.x, p0.y - 2 * p1.y + p2.y), Math.hypot(p1.x - 2 * p2.x + p3.x, p1.y - 2 * p2.y + p3.y));
      const n = divisions(turn(p0, p1, p2) + turn(p1, p2, p3), dev, perQuarter);
      for (let i = 1; i <= n; i++) {
        const t = i / n, u = 1 - t, a = u * u * u, b = 3 * u * u * t, d = 3 * u * t * t, e = t * t * t;
        put(a * p0.x + b * p1.x + d * p2.x + e * p3.x, a * p0.y + b * p1.y + d * p2.y + e * p3.y);
      }
    } else if (c.type === 'Z') close();
  }
  close();
  return out;
}

/** Signed area of a closed polyline: positive when it runs counter-clockwise (y up). */
export function polyArea(pts: readonly P[]): number {
  let a = 0;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) a += pts[j]!.x * pts[i]!.y - pts[i]!.x * pts[j]!.y;
  return a / 2;
}

/** Winding number of closed polylines around (x, y): +1 for each counter-clockwise turn, −1 for each clockwise one. */
export function windingAt(contours: readonly (readonly P[])[], x: number, y: number): number {
  let w = 0;
  for (const c of contours) {
    for (let i = 0, j = c.length - 1; i < c.length; j = i++) {
      const a = c[j]!, b = c[i]!;
      if (a.y <= y) {
        if (b.y > y && (b.x - a.x) * (y - a.y) - (x - a.x) * (b.y - a.y) > 0) w++;
      } else if (b.y <= y && (b.x - a.x) * (y - a.y) - (x - a.x) * (b.y - a.y) < 0) w--;
    }
  }
  return w;
}

/** Drops points where a loop runs straight on (a merged edge's cut points), until none are left. */
function straighten(loop: P[]): P[] {
  let pts = loop, again = true;
  while (again && pts.length > 3) {
    again = false;
    const out: P[] = [];
    for (let i = 0; i < pts.length; i++) {
      const a = out[out.length - 1] ?? pts[pts.length - 1]!, b = pts[i]!, c = pts[(i + 1) % pts.length]!;
      const ux = b.x - a.x, uy = b.y - a.y, vx = c.x - b.x, vy = c.y - b.y;
      if (Math.abs(ux * vy - uy * vx) <= 1e-9 * Math.hypot(ux, uy) * Math.hypot(vx, vy) && ux * vx + uy * vy > 0) {
        again = true;
        continue;
      }
      out.push(b);
    }
    pts = out;
  }
  return pts;
}

/**
 * What the nonzero rule fills, outlined by simple closed polylines: outlines counter-clockwise, counters clockwise,
 * none crossing another. Contours that neither cross nor touch come back as they are (toShapes nests them). Otherwise
 * every edge is cut where another crosses it, touches it or runs along it; a piece is kept where it separates filled
 * from empty (the winding numbers just either side of it, from the original contours), turned so the fill is on its
 * left, and the pieces are chained into loops, taking the sharpest clockwise turn at a junction so that loops which
 * only touch come apart. O(n²) in the points: a few milliseconds a glyph, once.
 */
export function unionNonzero(contours: readonly (readonly P[])[]): P[][] {
  interface Edge { a: P; b: P; c: number; i: number; n: number; cuts: { t: number; p: P }[]; x0: number; x1: number; y0: number; y1: number }
  const edges: Edge[] = [];
  contours.forEach((c, ci) => {
    for (let i = 0; i < c.length; i++) {
      const a = c[i]!, b = c[(i + 1) % c.length]!;
      edges.push({ a, b, c: ci, i, n: c.length, cuts: [], x0: Math.min(a.x, b.x) - EPS, x1: Math.max(a.x, b.x) + EPS, y0: Math.min(a.y, b.y) - EPS, y1: Math.max(a.y, b.y) + EPS });
    }
  });
  const along = (e: Edge, p: P) => {
    const dx = e.b.x - e.a.x, dy = e.b.y - e.a.y;
    return ((p.x - e.a.x) * dx + (p.y - e.a.y) * dy) / (dx * dx + dy * dy);
  };
  /** Records where e and f cut each other; true if they meet anywhere but the corner two neighbours share. */
  const meet = (e: Edge, f: Edge): boolean => {
    const d1x = e.b.x - e.a.x, d1y = e.b.y - e.a.y, d2x = f.b.x - f.a.x, d2y = f.b.y - f.a.y;
    const l1 = Math.hypot(d1x, d1y), l2 = Math.hypot(d2x, d2y);
    if (l1 === 0 || l2 === 0) return false;
    const ex = f.a.x - e.a.x, ey = f.a.y - e.a.y, den = d1x * d2y - d1y * d2x;
    const tt = EPS / l1, tu = EPS / l2;
    if (Math.abs(den) > 1e-12 * l1 * l2) {
      const t = (ex * d2y - ey * d2x) / den, u = (ex * d1y - ey * d1x) / den;
      if (t < -tt || t > 1 + tt || u < -tu || u > 1 + tu) return false;
      const tin = t > tt && t < 1 - tt, uin = u > tu && u < 1 - tu;
      if (tin && uin) {
        const p = { x: e.a.x + t * d1x, y: e.a.y + t * d1y };
        e.cuts.push({ t, p });
        f.cuts.push({ t: u, p });
      } else if (tin) {
        const p = u < 0.5 ? f.a : f.b; // f ends on e
        e.cuts.push({ t: along(e, p), p });
      } else if (uin) {
        const p = t < 0.5 ? e.a : e.b; // e ends on f
        f.cuts.push({ t: along(f, p), p });
      } else {
        // end to end: the corner of two neighbours, or two contours (or one) touching at a point
        const neighbours = e.c === f.c && ((e.i + 1) % e.n === f.i || (f.i + 1) % f.n === e.i);
        return !neighbours;
      }
      return true;
    }
    if (Math.abs(ex * d1y - ey * d1x) / l1 > EPS) return false; // parallel, apart
    // on one line: cut each where the other ends inside it, and meet if they share any length
    let hit = false;
    for (const p of [f.a, f.b]) {
      const t = along(e, p);
      if (t > tt && t < 1 - tt) { e.cuts.push({ t, p }); hit = true; }
    }
    for (const p of [e.a, e.b]) {
      const u = along(f, p);
      if (u > tu && u < 1 - tu) { f.cuts.push({ t: u, p }); hit = true; }
    }
    const ta = along(e, f.a), tb = along(e, f.b);
    return hit || Math.min(1, Math.max(ta, tb)) - Math.max(0, Math.min(ta, tb)) > tt;
  };

  let met = false;
  for (let i = 0; i < edges.length; i++) {
    const e = edges[i]!;
    for (let j = i + 1; j < edges.length; j++) {
      const f = edges[j]!;
      if (f.x0 > e.x1 || f.x1 < e.x0 || f.y0 > e.y1 || f.y1 < e.y0) continue;
      if (meet(e, f)) met = true;
    }
  }
  if (!met) return contours.map((c) => straighten(c.map((p) => ({ x: p.x, y: p.y }))));

  // the pieces, between shared vertices (points within EPS are one vertex)
  const verts: P[] = [], grid = new Map<string, number[]>(), CELL = 4 * EPS;
  const vid = (p: P) => {
    const gx = Math.round(p.x / CELL), gy = Math.round(p.y / CELL);
    for (let dx = -1; dx <= 1; dx++) {
      for (let dy = -1; dy <= 1; dy++) {
        for (const k of grid.get(`${gx + dx} ${gy + dy}`) ?? []) {
          if (Math.abs(verts[k]!.x - p.x) <= EPS && Math.abs(verts[k]!.y - p.y) <= EPS) return k;
        }
      }
    }
    const key = `${gx} ${gy}`;
    let cell = grid.get(key);
    if (!cell) grid.set(key, (cell = []));
    cell.push(verts.length);
    verts.push({ x: p.x, y: p.y });
    return verts.length - 1;
  };
  const pieces = new Map<string, [number, number]>(); // one per vertex pair: pieces lying on each other count once
  for (const e of edges) {
    e.cuts.sort((p, q) => p.t - q.t);
    let prev = vid(e.a);
    for (const p of [...e.cuts.map((c) => c.p), e.b]) {
      const k = vid(p);
      if (k === prev) continue;
      const key = prev < k ? `${prev} ${k}` : `${k} ${prev}`;
      if (!pieces.has(key)) pieces.set(key, [prev, k]);
      prev = k;
    }
  }

  // keep the boundary, fill on the left
  const from: number[] = [], to: number[] = [], leaving = new Map<number, number[]>();
  for (const [u, v] of pieces.values()) {
    const a = verts[u]!, b = verts[v]!, dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy);
    const off = Math.min(1e-6, len / 8), nx = (-dy / len) * off, ny = (dx / len) * off;
    const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
    const left = windingAt(contours, mx + nx, my + ny) !== 0, right = windingAt(contours, mx - nx, my - ny) !== 0;
    if (left === right) continue;
    const s = left ? u : v;
    from.push(s);
    to.push(left ? v : u);
    let l = leaving.get(s);
    if (!l) leaving.set(s, (l = []));
    l.push(from.length - 1);
  }

  // chain into loops
  const used = new Uint8Array(from.length), loops: P[][] = [];
  for (let e0 = 0; e0 < from.length; e0++) {
    if (used[e0]) continue;
    const loop: P[] = [];
    let e = e0, closed = false;
    while (!used[e]) {
      used[e] = 1;
      const a = verts[from[e]!]!, b = verts[to[e]!]!;
      loop.push(a);
      const bx = a.x - b.x, by = a.y - b.y; // back the way we came
      let next = -1, best = Infinity;
      for (const o of leaving.get(to[e]!) ?? []) {
        const c = verts[to[o]!]!, ox = c.x - b.x, oy = c.y - b.y;
        let cw = -Math.atan2(bx * oy - by * ox, bx * ox + by * oy); // clockwise from the way back, in (0, 2π]
        if (cw <= 0) cw += 2 * Math.PI;
        if (cw < best) { best = cw; next = o; }
      }
      if (next === e0) { closed = true; break; }
      if (next < 0) break;
      e = next;
    }
    if (closed) loops.push(loop);
  }
  return loops.map(straighten).filter((l) => l.length >= 3 && Math.abs(polyArea(l)) > MIN_AREA);
}

/** Loops as THREE.Shapes: through a ShapePath and toShapes, which nests each counter in the outline around it. */
function nest(loops: readonly (readonly P[])[]): THREE.Shape[] {
  const sp = new THREE.ShapePath();
  for (const l of loops) {
    sp.moveTo(l[0]!.x, l[0]!.y);
    for (let i = 1; i < l.length; i++) sp.lineTo(l[i]!.x, l[i]!.y);
    sp.lineTo(l[0]!.x, l[0]!.y);
  }
  return sp.toShapes();
}

/** Shapes (em, y up) for contours filled by the nonzero rule: overlaps merged, counters nested in their outlines. */
export const shapesOf = (contours: readonly (readonly P[])[]): THREE.Shape[] => nest(unionNonzero(contours));

const OUTLINES = new Map<string, P[][]>();
function outline(family: string, ch: string, perQuarter: number): P[][] {
  const key = `${family}\u0000${ch}\u0000${perQuarter}`;
  let o = OUTLINES.get(key);
  if (!o) {
    const f = ot(family);
    o = unionNonzero(flatten(f.charToGlyph(ch).path.commands, f.unitsPerEm, perQuarter));
    OUTLINES.set(key, o);
  }
  return o;
}

/**
 * A glyph's outline as THREE.Shapes: unit em, y up, at the glyph's origin (left side bearing included, baseline at 0),
 * overlaps merged and every counter a hole of the outline around it. `curveSegments` is per quarter turn.
 */
export function glyphShapes(family: string, ch: string, curveSegments = CURVE_SEGMENTS): THREE.Shape[] {
  return nest(outline(family, ch, curveSegments));
}

// ------------------------------------------------------------------------------------------------------- geometry

/**
 * Normals for an extruded glyph whose face is at z = 0 and back at −depth (after the translate in `build`): the lids
 * (group 0) flat; the sides (group 1) smoothed over neighbouring faces within CREASE of each other, weighted by corner
 * angle, then pinned: the bevel's first row takes the face's normal, the walls' rows are level. On a round bevel that is
 * exact at every row (0°, 22.5°, 45°, 67.5°, 90°), so the light rolls off the face, over the bevel, onto the wall.
 */
function shade(geo: THREE.BufferGeometry, depth: number, bevel: number) {
  const P = geo.getAttribute('position').array as Float32Array, N = new Float32Array(P.length);
  const tol = 1e-5 * depth;
  const tris: number[] = [];
  for (const g of geo.groups) {
    for (let i = g.start; i < g.start + g.count; i++) {
      if (g.materialIndex === 0) N[3 * i + 2] = P[3 * i + 2]! > -depth / 2 ? 1 : -1;
      else if ((i - g.start) % 3 === 0) tris.push(i);
    }
  }
  const fn = new Float64Array(tris.length * 3), angle = new Float64Array(tris.length * 3);
  const at = new Map<string, number[]>(); // position → corners (triangle * 3 + corner) there
  const v = (i: number) => new THREE.Vector3(P[3 * i], P[3 * i + 1], P[3 * i + 2]);
  tris.forEach((i, k) => {
    const [a, b, c] = [v(i), v(i + 1), v(i + 2)];
    const n = new THREE.Vector3().subVectors(b, a).cross(new THREE.Vector3().subVectors(c, a));
    const len = n.length();
    if (len > 1e-20) n.divideScalar(len);
    else n.set(0, 0, 0);
    fn.set([n.x, n.y, n.z], 3 * k);
    const corner = (p: THREE.Vector3, q: THREE.Vector3, r: THREE.Vector3) => {
      const u = q.clone().sub(p), w = r.clone().sub(p);
      return u.lengthSq() > 0 && w.lengthSq() > 0 ? u.angleTo(w) : 0;
    };
    angle.set([corner(a, b, c), corner(b, c, a), corner(c, a, b)], 3 * k);
    for (let j = 0; j < 3; j++) {
      const key = `${P[3 * (i + j)]} ${P[3 * (i + j) + 1]} ${P[3 * (i + j) + 2]}`;
      let l = at.get(key);
      if (!l) at.set(key, (l = []));
      l.push(3 * k + j);
    }
  });
  const cosC = Math.cos(CREASE);
  for (const corners of at.values()) {
    for (const kc of corners) {
      const k = (kc / 3) | 0, i = tris[k]! + (kc % 3);
      let x = 0, y = 0, z = 0;
      for (const kc2 of corners) {
        const k2 = (kc2 / 3) | 0;
        const d = fn[3 * k]! * fn[3 * k2]! + fn[3 * k + 1]! * fn[3 * k2 + 1]! + fn[3 * k + 2]! * fn[3 * k2 + 2]!;
        if (d < cosC) continue;
        x += angle[kc2]! * fn[3 * k2]!;
        y += angle[kc2]! * fn[3 * k2 + 1]!;
        z += angle[kc2]! * fn[3 * k2 + 2]!;
      }
      const pz = P[3 * i + 2]!;
      if (bevel > 0 && Math.abs(pz) < tol) (x = 0), (y = 0), (z = 1); // the bevel's first row: the face's normal
      else if (bevel > 0 && Math.abs(pz + depth) < tol) (x = 0), (y = 0), (z = -1);
      else if (bevel <= 0 || (pz <= -bevel + tol && pz >= -depth + bevel - tol)) z = 0; // a wall row: level
      const len = Math.hypot(x, y, z) || 1;
      N[3 * i] = x / len;
      N[3 * i + 1] = y / len;
      N[3 * i + 2] = z / len;
    }
  }
  geo.setAttribute('normal', new THREE.BufferAttribute(N, 3));
}

interface GlyphGeo { geo: THREE.BufferGeometry; pivot: THREE.Vector3; refs: number }
const GEOS = new Map<string, GlyphGeo>();

/**
 * The extruded glyph, in em: the face at z = 0 (depth runs back to −depth), then moved so the pivot is the origin. Null
 * for a glyph with no outline.
 */
function build(family: string, ch: string, depth: number, bevel: number, perQuarter: number): Omit<GlyphGeo, 'refs'> | null {
  const shapes = glyphShapes(family, ch, perQuarter);
  if (!shapes.length) return null;
  const b = Math.max(0, Math.min(bevel, 0.45 * depth));
  const geo = new THREE.ExtrudeGeometry(shapes, {
    depth: depth - 2 * b, steps: 1, curveSegments: 1,
    bevelEnabled: b > 0, bevelThickness: b, bevelSize: b, bevelOffset: -b, bevelSegments: BEVEL_SEGMENTS,
  });
  geo.deleteAttribute('uv');
  geo.translate(0, 0, b - depth); // three extrudes over [−b, depth − b]
  shade(geo, depth, b);
  const z = geo.getAttribute('position'), behind = new Float32Array(z.count);
  for (let i = 0; i < z.count; i++) behind[i] = Math.min(depth, Math.max(0, -z.getZ(i)));
  geo.setAttribute('type3dDepth', new THREE.BufferAttribute(behind, 1)); // em behind the face, for the accent's rim
  const f = ot(family), upm = f.unitsPerEm;
  const xHeight = ((f.tables.os2?.sxHeight as number | undefined) || 0.5 * upm) / upm;
  const pivot = new THREE.Vector3((f.charToGlyph(ch).advanceWidth ?? 0) / upm / 2, xHeight / 2, -depth / 2);
  geo.translate(-pivot.x, -pivot.y, -pivot.z);
  geo.computeBoundingBox();
  geo.computeBoundingSphere();
  return { geo, pivot };
}

function acquire(family: string, ch: string, depth: number, bevel: number, perQuarter: number) {
  const key = [family, ch, depth, bevel, perQuarter].join('\u0000');
  let g = GEOS.get(key);
  if (!g) {
    const built = build(family, ch, depth, bevel, perQuarter);
    if (!built) return null;
    GEOS.set(key, (g = { ...built, refs: 0 }));
  }
  g.refs++;
  return { key, g };
}

function release(key: string) {
  const g = GEOS.get(key);
  if (!g || --g.refs > 0) return;
  g.geo.dispose();
  GEOS.delete(key);
}

// --------------------------------------------------------------------------------------------------------- Type3D

export interface Type3DOpts {
  family: string;
  /** World units per em. */
  size: number;
  /** Front to back, bevels included, in em (default DEPTH, 0.16). */
  depth?: number;
  /** Radius of the round bevel, in em (default BEVEL, 0.012). */
  bevel?: number;
  /** Curve segments per quarter turn (default 12). */
  curveSegments?: number;
  /** Extra letter spacing, in em (as layout()'s tracking). */
  tracking?: number;
}

export interface Glyph3D {
  ch: string;
  /** The glyph's mesh, pivoted at its centre; at rest it is at `home` with scale `size` and no rotation. */
  mesh: THREE.Mesh;
  /** Left edge (world units from the text origin): layout()'s kerned x. */
  x: number;
  /** Advance width (world units). */
  w: number;
  /** Index of the word it belongs to (words are split by white space). */
  word: number;
  /** Index of the character in the text (as layout().glyphs[i].i). */
  i: number;
  /** Rest position of the mesh (group space): mid-advance, half the x-height, mid-depth, so the face is at z = 0. */
  home: THREE.Vector3;
}

/**
 * A line of extruded type. The group's origin is the text origin (left end, baseline) on the face plane (z = 0); the
 * line runs along +x and is `width` long. White space makes no glyphs. Materials belong to the caller: pass one for the
 * whole line, or a function to choose per glyph (an accent word by `word`); Type3D never disposes them.
 */
export class Type3D {
  group = new THREE.Group();
  glyphs: Glyph3D[] = [];
  width: number;
  /** World units per em (a glyph's rest scale). */
  size: number;
  private keys: string[] = [];

  constructor(
    text: string,
    opts: Type3DOpts,
    material: THREE.Material | ((g: { ch: string; i: number; word: number }) => THREE.Material),
  ) {
    const { family, size, depth = DEPTH, bevel = BEVEL, curveSegments = CURVE_SEGMENTS, tracking = 0 } = opts;
    this.size = size;
    const lay = layout(text, family, UNIT_PX, tracking * UNIT_PX), k = size / UNIT_PX;
    this.width = lay.width * k;
    let word = -1, gap = true;
    for (const g of lay.glyphs) {
      if (/\s/u.test(g.ch)) {
        gap = true;
        continue;
      }
      if (gap) (word++), (gap = false);
      const got = acquire(family, g.ch, depth, bevel, curveSegments);
      if (!got) continue;
      this.keys.push(got.key);
      const mat = typeof material === 'function' ? material({ ch: g.ch, i: g.i, word }) : material;
      const mesh = new THREE.Mesh(got.g.geo, mat);
      mesh.name = g.ch;
      const home = new THREE.Vector3(g.x * k + got.g.pivot.x * size, got.g.pivot.y * size, got.g.pivot.z * size);
      mesh.position.copy(home);
      mesh.scale.setScalar(size);
      this.group.add(mesh);
      this.glyphs.push({ ch: g.ch, mesh, x: g.x * k, w: g.w * k, word, i: g.i, home });
    }
  }

  /** Every glyph back at rest: at home, unrotated, at scale `size`. */
  reset() {
    for (const g of this.glyphs) {
      g.mesh.position.copy(g.home);
      g.mesh.rotation.set(0, 0, 0);
      g.mesh.scale.setScalar(this.size);
    }
  }

  /** Removes the meshes and lets go of the shared geometry (freed when no Type3D uses it). Materials are the caller's. */
  dispose() {
    for (const g of this.glyphs) this.group.remove(g.mesh);
    for (const key of this.keys) release(key);
    this.keys = [];
    this.glyphs = [];
  }
}

// ------------------------------------------------------------------------------------------------------ materials

/**
 * The diff glow's shape. Across the edge (1 − |n.z| of the object-space normal: 0 on the face, 1 on a wall) it is
 * nothing on the face and the inner bevel, which stay satin bone and catch the key, and whole from the outer bevel onto
 * the wall. Along the depth it is whole down to the seam where the bevel meets the wall (RIM_SEAM em behind the face,
 * the default bevel) and dies away behind it within a few hundredths of an em (RIM_FADE): a line of light at the edge
 * whose bloom carries the colour, over bone walls. A whole wall at glow level shows as a pastel slab instead (the tone
 * shoulder whitens any emission above the palette colour), and a glowing bevel as a neon outline round the face.
 */
const RIM_EDGE: readonly [number, number] = [0.25, 0.75];
/** Where the seam is for the default bevel; a bevel of another size moves its line by the difference (hundredths of an em). */
const RIM_SEAM = BEVEL;
const RIM_FADE = 0.025;
/** How much of the bone surface the glow takes over where it is whole: the lit edge reads as moss light, not pale mint. */
const RIM_TAKE = 0.8;
const RIM_SURFACE_GLSL = /* glsl */ `
	material.diffuseColor *= 1.0 - ${RIM_TAKE.toFixed(4)} * type3dK;
	#ifdef USE_SHEEN
		material.sheenColor *= 1.0 - ${RIM_TAKE.toFixed(4)} * type3dK;
	#endif`;
const RIM_GLSL = /* glsl */ `
varying vec3 vType3dN;
varying float vType3dD;
float type3dRim( vec3 n, float d ) {
	float edge = smoothstep( ${RIM_EDGE[0].toFixed(4)}, ${RIM_EDGE[1].toFixed(4)}, 1.0 - abs( normalize( n ).z ) );
	return edge * exp( -max( d - ${RIM_SEAM.toFixed(4)}, 0.0 ) / ${RIM_FADE.toFixed(4)} );
}`;

const bone = () => new THREE.Color().setRGB(LIN.bone[0], LIN.bone[1], LIN.bone[2]);

function satinBone(): THREE.MeshPhysicalMaterial {
  return new THREE.MeshPhysicalMaterial({
    color: bone(), roughness: 0.38, metalness: 0,
    clearcoat: 0.25, clearcoatRoughness: 0.12,
    sheen: 0.3, sheenRoughness: 0.6, sheenColor: bone(),
  });
}

export const Mat = {
  /** The film's type surface: satin bone, a thin clearcoat for the studio's highlights, sheen at grazing angles. */
  satinBone,
  /**
   * Satin bone with the diff glow: the edge emits `c` at glow level `emissive` (glow(), the film's one way to set an
   * emissive level; GLOW_LEVEL by default) as a line at the seam behind the bevel that fades back along the wall, and
   * gives up most of its bone there; the face emits nothing. Animate `emissiveIntensity` to bring the glow up or pulse
   * it. Made for Type3D geometry (the fade reads its `type3dDepth` attribute; elsewhere the whole edge takes the seam's
   * level). A new material; the caller owns it.
   */
  accent(c: 'blood' | 'moss', emissive = GLOW_LEVEL): THREE.MeshPhysicalMaterial {
    const m = satinBone();
    const [r, g, b] = glow(c, 1);
    m.emissive.setRGB(r, g, b);
    m.emissiveIntensity = emissive;
    m.onBeforeCompile = (sh) => {
      sh.vertexShader = sh.vertexShader
        .replace('#include <common>', '#include <common>\nattribute float type3dDepth;\nvarying vec3 vType3dN;\nvarying float vType3dD;')
        .replace('#include <beginnormal_vertex>', '#include <beginnormal_vertex>\n\tvType3dN = objectNormal;\n\tvType3dD = type3dDepth;');
      sh.fragmentShader = sh.fragmentShader
        .replace('#include <common>', `#include <common>\n${RIM_GLSL}`)
        .replace('#include <emissivemap_fragment>', '#include <emissivemap_fragment>\n\tfloat type3dK = type3dRim( vType3dN, vType3dD );\n\ttotalEmissiveRadiance *= type3dK;')
        .replace('#include <lights_physical_fragment>', `#include <lights_physical_fragment>\n${RIM_SURFACE_GLSL}`);
    };
    m.customProgramCacheKey = () => 'type3d-accent-rim';
    return m;
  },
};
