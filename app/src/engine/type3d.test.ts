import { afterAll, beforeAll, describe, expect, spyOn, test } from 'bun:test';
import path from 'node:path';
import * as opentype from 'opentype.js';
import * as THREE from 'three';
import { F, layout, loadFonts, ot } from './type';
import { GLOW_LEVEL, glow } from './look';
import { LIN } from './palette';
import { BEVEL, DEPTH, Mat, Type3D, flatten, glyphShapes, polyArea, shapesOf, unionNonzero, windingAt, type P } from './type3d';

// ------------------------------------------------------------------------------------------------ a browser for bun
// type.ts reads fonts through fetch + FontFace (loadFonts) and measures text with Canvas2D (layout). Bun has neither, so
// the fonts come off disk and a stand-in context measures the way Chrome sets a line: each glyph's advance plus the
// font's GPOS pair kerning (opentype.js). Type3D must place glyphs wherever layout() says, whatever does the measuring.

const FONTS = path.resolve(import.meta.dir, '../../public');
const parsed = new Map<string, opentype.Font>();
const saved = { fetch: globalThis.fetch, document: (globalThis as any).document, FontFace: (globalThis as any).FontFace };

const measure = {
  font: '',
  measureText(s: string) {
    const m = /^([\d.]+)px "(.+)"$/.exec(this.font);
    if (!m) throw new Error(`unexpected font string ${this.font}`);
    const size = +m[1]!, f = parsed.get(m[2]!)!;
    const gs = Array.from(s).map((ch) => f.charToGlyph(ch));
    let w = 0;
    gs.forEach((g, i) => { w += g.advanceWidth! + (i > 0 ? f.getKerningValue(gs[i - 1]!, g) : 0); });
    const k = size / f.unitsPerEm;
    return { width: w * k, fontBoundingBoxAscent: f.ascender * k, fontBoundingBoxDescent: -f.descender * k };
  },
};

beforeAll(async () => {
  (globalThis as any).fetch = async (url: string) => new Response(Bun.file(path.join(FONTS, String(url))));
  (globalThis as any).FontFace = class {
    constructor(family: string, buf: ArrayBuffer) { parsed.set(family, opentype.parse(buf)); }
    async load() { return this; }
  };
  (globalThis as any).document = {
    fonts: { add() {}, ready: Promise.resolve() },
    createElement: () => ({ getContext: () => measure }),
  };
  await loadFonts();
});

afterAll(() => {
  globalThis.fetch = saved.fetch;
  (globalThis as any).document = saved.document;
  (globalThis as any).FontFace = saved.FontFace;
});

const FAM = 'Bricolage-1000-600';

// -------------------------------------------------------------------------------------------------------- helpers

const pts = (s: THREE.Path) => s.getPoints(1).map((v) => ({ x: v.x, y: v.y }));
/** Even-odd point-in-polygon (the polygons here are simple). */
function inPoly(poly: P[], x: number, y: number) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[i]!, b = poly[j]!;
    if ((a.y > y) !== (b.y > y) && x < ((b.x - a.x) * (y - a.y)) / (b.y - a.y) + a.x) inside = !inside;
  }
  return inside;
}
/** A point test for what shapes fill: inside an outline and outside its counters. */
function filler(shapes: THREE.Shape[]) {
  const polys = shapes.map((s) => ({ o: pts(s), h: s.holes.map(pts) }));
  return (x: number, y: number) => polys.some((s) => inPoly(s.o, x, y) && !s.h.some((h) => inPoly(h, x, y)));
}
/** Filled area of shapes: outlines minus counters. */
const shapesArea = (shapes: THREE.Shape[]) =>
  shapes.reduce((a, s) => a + Math.abs(polyArea(pts(s))) - s.holes.reduce((b, h) => b + Math.abs(polyArea(pts(h))), 0), 0);
const counts = (shapes: THREE.Shape[]) => shapes.map((s) => s.holes.length).sort();
/** Seeded points (mulberry32) in a box. */
function* scatter(n: number, x0: number, y0: number, x1: number, y1: number, seed = 7) {
  let s = seed >>> 0;
  const r = () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  for (let i = 0; i < n; i++) yield [x0 + r() * (x1 - x0), y0 + r() * (y1 - y0)] as const;
}
const raw = (ch: string, fam = FAM) => flatten(ot(fam).charToGlyph(ch).path.commands, ot(fam).unitsPerEm);
const square = (x0: number, y0: number, x1: number, y1: number, ccw = true): P[] => {
  const q = [{ x: x0, y: y0 }, { x: x1, y: y0 }, { x: x1, y: y1 }, { x: x0, y: y1 }];
  return ccw ? q : q.reverse();
};

// ---------------------------------------------------------------------------------------------------- the outlines

describe('glyphShapes', () => {
  test("'o' is one shape with one counter", () => {
    const s = glyphShapes(FAM, 'o');
    expect(s.length).toBe(1);
    expect(s[0]!.holes.length).toBe(1);
  });

  test("'i' is two shapes, the stem and the dot", () => {
    const s = glyphShapes(FAM, 'i');
    expect(s.length).toBe(2);
    expect(counts(s)).toEqual([0, 0]);
  });

  test('a, e and g keep real counters (the font draws the e as one contour whose crossbar crosses the bowl)', () => {
    expect(raw('e').length).toBe(1); // one self-crossing contour: extruded as it stands, earcut fills the eye
    for (const [ch, holes] of [['a', [1]], ['e', [1]], ['g', [2]], ['B', [2]], ['R', [1]]] as const) {
      const s = glyphShapes(FAM, ch);
      expect({ ch, holes: counts(s) }).toEqual({ ch, holes: [...holes] });
    }
  });

  test('overlapping contours merge into one outline: the crossbars of H, # and + and the bars of A, E and 4', () => {
    for (const [ch, holes] of [['H', [0]], ['+', [0]], ['#', [1]], ['A', [1]], ['E', [0]], ['4', [1]], ['8', [2]], ['&', [2]]] as const) {
      expect({ ch, holes: counts(glyphShapes(FAM, ch)) }).toEqual({ ch, holes: [...holes] });
    }
  });

  test("the shapes fill exactly what the font's contours fill by the nonzero rule", () => {
    for (const fam of [FAM, 'Bricolage-750-800', 'Bricolage-1000-300']) {
      for (const ch of 'aegmoy8&@#$AEHRT4%?') {
        const c = raw(ch, fam), filled = filler(glyphShapes(fam, ch));
        const xs = c.flat().map((p) => p.x), ys = c.flat().map((p) => p.y);
        let bad = 0;
        for (const [x, y] of scatter(1500, Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys))) {
          if (filled(x, y) !== (windingAt(c, x, y) !== 0)) bad++;
        }
        expect({ fam, ch, bad }).toEqual({ fam, ch, bad: 0 });
      }
    }
  });

  test('contour direction does not matter: counter-clockwise (CFF) outlines give the same shapes as clockwise (TrueType)', () => {
    for (const ch of 'oe8&gA') {
      const fwd = glyphShapes(FAM, ch), rev = shapesOf(raw(ch).map((c) => [...c].reverse()));
      expect(counts(rev)).toEqual(counts(fwd));
      expect(shapesArea(rev)).toBeCloseTo(shapesArea(fwd), 9);
    }
  });

  test('curves are flattened finely: no chord strays more than 0.0002 em (0.2 px at 1000 px per em) from the curve', () => {
    const segDist = (p: P, a: P, b: P) => {
      const dx = b.x - a.x, dy = b.y - a.y, l2 = dx * dx + dy * dy;
      const t = l2 ? Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / l2)) : 0;
      return Math.hypot(p.x - a.x - t * dx, p.y - a.y - t * dy);
    };
    for (const ch of 'oeSg@&') {
      const f = ot(FAM), cmds = f.charToGlyph(ch).path.commands;
      const fine = flatten(cmds, f.unitsPerEm, 400), coarse = flatten(cmds, f.unitsPerEm);
      expect(coarse.length).toBe(fine.length);
      let worst = 0;
      coarse.forEach((c, ci) => {
        const ref = fine[ci]!;
        c.forEach((a, i) => {
          const b = c[(i + 1) % c.length]!, m = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
          let d = Infinity;
          for (let j = 0; j < ref.length; j++) d = Math.min(d, segDist(m, ref[j]!, ref[(j + 1) % ref.length]!));
          worst = Math.max(worst, d);
          expect(a.x !== b.x || a.y !== b.y).toBe(true); // no repeated points, the closing one included
        });
      });
      expect({ ch, over: worst > 2e-4 }).toEqual({ ch, over: false });
    }
  });

  test('shapes are in em, y up, where the font puts them', () => {
    const g = ot(FAM).charToGlyph('o'), upm = ot(FAM).unitsPerEm;
    const b = new THREE.Box2();
    for (const s of glyphShapes(FAM, 'o')) for (const p of s.getPoints()) b.expandByPoint(p);
    expect(b.min.x).toBeCloseTo(g.xMin! / upm, 3);
    expect(b.max.x).toBeCloseTo(g.xMax! / upm, 3);
    expect(b.min.y).toBeCloseTo(g.yMin! / upm, 3); // below the baseline: the overshoot
    expect(b.max.y).toBeCloseTo(g.yMax! / upm, 3);
  });
});

describe('unionNonzero', () => {
  const shapes = (cs: P[][]) => shapesOf(cs);

  test('two overlapping squares, drawn either way round, are one outline', () => {
    for (const ccw of [true, false]) {
      const s = shapes([square(0, 0, 2, 2, ccw), square(1, 1, 3, 3, ccw)]);
      expect(counts(s)).toEqual([0]);
      expect(shapesArea(s)).toBeCloseTo(7, 9);
    }
  });

  test('squares that share an edge merge, with no seam left between them', () => {
    const loops = unionNonzero([square(0, 0, 1, 1), square(1, 0, 2, 1)]);
    expect(loops.length).toBe(1);
    expect(loops[0]!.length).toBe(4); // the shared edge and its end points are gone
    expect(polyArea(loops[0]!)).toBeCloseTo(2, 9);
  });

  test('a counter comes out clockwise inside a counter-clockwise outline, whichever way the font drew them', () => {
    for (const [outer, inner] of [[true, false], [false, true]]) {
      const s = shapes([square(0, 0, 3, 3, outer), square(1, 1, 2, 2, inner), square(-1, 1.2, 0.5, 1.8, outer)]); // a bar poked in from the left
      expect(counts(s)).toEqual([1]);
      expect(shapesArea(s)).toBeCloseTo(9 - 1 + 0.6 * 1, 9);
      const loops = unionNonzero([square(0, 0, 3, 3, outer), square(1, 1, 2, 2, inner), square(-1, 1.2, 0.5, 1.8, outer)]);
      expect(loops.map((l) => Math.sign(polyArea(l))).sort()).toEqual([-1, 1]);
    }
  });

  test('a self-crossing contour is split where it crosses (a bow tie is two triangles by the nonzero rule)', () => {
    const tie = [{ x: 0, y: 0 }, { x: 2, y: 2 }, { x: 2, y: 0 }, { x: 0, y: 2 }];
    const s = shapes([tie]);
    expect(counts(s)).toEqual([0, 0]);
    expect(shapesArea(s)).toBeCloseTo(2, 9);
  });
});

// --------------------------------------------------------------------------------------------------------- Type3D

describe('Type3D', () => {
  const SIZE = 0.37; // world units per em
  const bone = new THREE.MeshBasicMaterial();

  test('a character the family lacks throws while authoring, naming it; an export (?export=1) warns once and goes on', () => {
    // Bricolage has no ✔: charToGlyph would give glyph 0, the font's .notdef box, extruded, while Canvas2D (layout(),
    // the flat line) draws a ✔ from a fallback font
    expect(() => new Type3D('ok ✔', { family: FAM, size: SIZE }, bone)).toThrow('no glyph for "✔" (U+2714)');
    expect(() => glyphShapes(FAM, '✔')).toThrow('U+2714');
    const saved = (globalThis as any).location;
    (globalThis as any).location = { search: '?export=1' };
    const warn = spyOn(console, 'warn').mockImplementation(() => {});
    try {
      const t = new Type3D('✔ ✔', { family: FAM, size: SIZE }, bone);
      expect(t.glyphs.map((g) => g.ch)).toEqual(['✔', '✔']);
      expect(warn).toHaveBeenCalledTimes(1);
      expect(String(warn.mock.calls[0]![0])).toContain('no glyph for "✔" (U+2714)');
      t.dispose();
    } finally {
      warn.mockRestore();
      (globalThis as any).location = saved;
    }
    // every character the film sets in 3D is there
    for (const [fam, text] of [[FAM, 'every memory has a commit − + “’” …'], [F.mono(500), '− +'], [F.mono(400), '3f9a1c2 (you 2026-07-26)']] as const) {
      new Type3D(text, { family: fam, size: SIZE }, bone).dispose();
    }
  });

  test("the width is layout()'s width × scale (within 1%)", () => {
    const t = new Type3D('commit', { family: FAM, size: SIZE }, bone);
    const lay = layout('commit', FAM, 120);
    expect(Math.abs(t.width - lay.width * (SIZE / 120)) / t.width).toBeLessThan(0.01);
    t.dispose();
  });

  test("each glyph sits at layout()'s kerned x × scale, and is as wide as its advance", () => {
    for (const text of ['commit', 'every memory has a commit']) {
      const t = new Type3D(text, { family: FAM, size: SIZE, tracking: 0.02 }, bone);
      const lay = layout(text, FAM, 120, 0.02 * 120), k = SIZE / 120;
      expect(t.glyphs.length).toBe(Array.from(text).filter((c) => c !== ' ').length);
      for (const g of t.glyphs) {
        expect(g.ch).toBe(lay.glyphs[g.i]!.ch);
        expect(g.x).toBeCloseTo(lay.glyphs[g.i]!.x * k, 9);
        expect(g.w).toBeCloseTo(lay.glyphs[g.i]!.w * k, 9);
      }
      t.dispose();
    }
  });

  test('the kerning is in: e–v and v–e sit tighter than their advances', () => {
    const t = new Type3D('every', { family: FAM, size: 1 }, bone);
    const [e, v, e2] = t.glyphs;
    expect(v!.x).toBeLessThan(e!.x + e!.w - 0.01); // Bricolage kerns e–v by −24/1000
    expect(e2!.x).toBeLessThan(v!.x + v!.w - 0.01); // and v–e by −31/1000
    t.dispose();
  });

  test('spaces make no glyphs; each glyph knows its word, and the material callback is asked per glyph', () => {
    const asked: { ch: string; i: number; word: number }[] = [];
    const moss = new THREE.MeshBasicMaterial();
    const t = new Type3D('every memory has a commit', { family: FAM, size: SIZE }, (g) => {
      asked.push(g);
      return g.word === 4 ? moss : bone;
    });
    expect(t.glyphs.map((g) => g.word).join('')).toBe('000001111112223444444');
    const words = 'every memory has a commit'.split(' ');
    words.forEach((w, k) => expect(t.glyphs.filter((g) => g.word === k).map((g) => g.ch).join('')).toBe(w));
    expect(asked.map((a) => a.ch).join('')).toBe('everymemoryhasacommit');
    expect(asked.map((a) => a.i)).toEqual(t.glyphs.map((g) => g.i));
    for (const g of t.glyphs) expect(g.mesh.material).toBe(g.word === 4 ? moss : bone);
    t.dispose();
  });

  test('walls stand on the outline (the face is inset), the face is at z = 0 and the back at −depth', () => {
    for (const [ch, depth, bevel] of [['o', DEPTH, BEVEL], ['e', 0.3, 0.02], ['H', DEPTH, BEVEL]] as const) {
      const t = new Type3D(`x${ch}`, { family: FAM, size: SIZE, depth, bevel }, bone);
      const g = t.glyphs[1]!;
      t.group.updateMatrixWorld(true);
      const box = new THREE.Box3().setFromObject(g.mesh);
      const ob = new THREE.Box2();
      for (const s of glyphShapes(FAM, ch)) for (const p of s.getPoints()) ob.expandByPoint(p);
      expect(box.min.x).toBeCloseTo(g.x + ob.min.x * SIZE, 6);
      expect(box.max.x).toBeCloseTo(g.x + ob.max.x * SIZE, 6);
      expect(box.min.y).toBeCloseTo(ob.min.y * SIZE, 6);
      expect(box.max.y).toBeCloseTo(ob.max.y * SIZE, 6);
      expect(box.max.z).toBeCloseTo(0, 7); // float32 positions
      expect(box.min.z).toBeCloseTo(-depth * SIZE, 7);
      // at rest a glyph is where the line put it: home is its pivot (mid-advance, half the x-height, mid-depth)
      expect(g.mesh.position.toArray()).toEqual(g.home.toArray());
      expect(g.home.x).toBeCloseTo(g.x + g.w / 2, 9);
      expect(g.home.z).toBeCloseTo((-depth / 2) * SIZE, 9);
      t.dispose();
    }
  });

  test("the counter of an extruded 'o' is open: no face triangle covers it, while the stroke is covered", () => {
    const t = new Type3D('o', { family: FAM, size: 1 }, bone);
    const g = t.glyphs[0]!;
    const geo = g.mesh.geometry, pos = geo.getAttribute('position'), nrm = geo.getAttribute('normal');
    const front: P[][] = [];
    for (let i = 0; i < pos.count; i += 3) {
      if ([0, 1, 2].every((k) => nrm.getZ(i + k) > 0.999999)) {
        front.push([0, 1, 2].map((k) => ({ x: pos.getX(i + k) + g.home.x, y: pos.getY(i + k) + g.home.y })));
      }
    }
    const covered = (x: number, y: number) => front.some((tri) => inPoly(tri, x, y));
    const [shape] = glyphShapes(FAM, 'o');
    const hole = pts(shape!.holes[0]!), outer = pts(shape!);
    const cx = hole.reduce((a, p) => a + p.x, 0) / hole.length, cy = hole.reduce((a, p) => a + p.y, 0) / hole.length;
    expect(covered(g.x + cx, cy)).toBe(false);
    // the middle of the left stroke, halfway between the outline and the counter at the counter's height
    const left = (poly: P[]) => poly.filter((p) => p.x < cx).reduce((a, p) => (Math.abs(p.y - cy) < Math.abs(a.y - cy) ? p : a));
    expect(covered(g.x + (left(outer).x + left(hole).x) / 2, cy)).toBe(true);
    t.dispose();
  });

  test('normals: flat faces, level walls, a bevel that turns smoothly between them, creased only at corners', () => {
    const t = new Type3D('ol', { family: FAM, size: 1 }, bone);
    for (const g of t.glyphs) {
      const geo = g.mesh.geometry, pos = geo.getAttribute('position'), nrm = geo.getAttribute('normal');
      const z0 = -g.home.z; // geometry z of the face (the pivot sits at mid-depth)
      const byPos = new Map<string, THREE.Vector3[]>();
      let bevelSeen = 0;
      for (let i = 0; i < pos.count; i++) {
        const z = pos.getZ(i) - z0; // 0 at the face, −DEPTH at the back
        const n = new THREE.Vector3(nrm.getX(i), nrm.getY(i), nrm.getZ(i));
        expect(Math.abs(n.length() - 1)).toBeLessThan(1e-5);
        if (Math.abs(z) < 1e-7) expect(n.z).toBeGreaterThan(0.999999); // the face and the bevel's top row
        else if (Math.abs(z + DEPTH) < 1e-7) expect(n.z).toBeLessThan(-0.999999);
        else if (z <= -BEVEL + 1e-7 && z >= -DEPTH + BEVEL - 1e-7) expect(Math.abs(n.z)).toBeLessThan(1e-6); // walls
        else {
          bevelSeen++;
          expect(Math.abs(n.z)).toBeGreaterThan(0.05); // part way round
          expect(Math.abs(n.z)).toBeLessThan(0.995);
        }
        const key = `${pos.getX(i)},${pos.getY(i)},${pos.getZ(i)}`;
        (byPos.get(key) ?? byPos.set(key, []).get(key)!).push(n);
      }
      expect(bevelSeen).toBeGreaterThan(0);
      // the 'o' is all curves: one normal per point. The 'l' has square corners: those points keep one normal per side
      let creased = 0;
      for (const ns of byPos.values()) if (ns.some((n) => n.angleTo(ns[0]!) > 0.5)) creased++;
      if (g.ch === 'o') expect(creased).toBe(0);
      else expect(creased).toBeGreaterThan(0);
    }
    t.dispose();
  });

  test("each vertex carries its distance behind the face, in em (the accent's glow fades back from the edge by it)", () => {
    for (const depth of [DEPTH, 0.3]) {
      const t = new Type3D('e', { family: FAM, size: 1, depth }, bone);
      const geo = t.glyphs[0]!.mesh.geometry, pos = geo.getAttribute('position'), d = geo.getAttribute('type3dDepth');
      expect(d.count).toBe(pos.count);
      let max = 0;
      for (let i = 0; i < pos.count; i++) {
        expect(Math.abs(d.getX(i) - (depth / 2 - pos.getZ(i)))).toBeLessThan(1e-6); // the pivot is at mid-depth
        max = Math.max(max, d.getX(i));
      }
      expect(max).toBeCloseTo(depth, 6);
      t.dispose();
    }
  });

  test('geometry is cached per (family, char, depth, bevel) and shared; the last dispose frees it', () => {
    const depth = 0.21; // a key no other test uses
    const a = new Type3D('oo', { family: FAM, size: 1, depth }, bone);
    const b = new Type3D('o', { family: FAM, size: 2, depth }, bone);
    const c = new Type3D('o', { family: FAM, size: 1, depth: 0.3 }, bone);
    const geo = a.glyphs[0]!.mesh.geometry;
    expect(a.glyphs[1]!.mesh.geometry).toBe(geo);
    expect(b.glyphs[0]!.mesh.geometry).toBe(geo);
    expect(c.glyphs[0]!.mesh.geometry).not.toBe(geo);
    let freed = 0;
    geo.addEventListener('dispose', () => freed++);
    a.dispose();
    expect(freed).toBe(0);
    expect(a.group.children.length).toBe(0);
    b.dispose();
    expect(freed).toBe(1);
    c.dispose();
    const d = new Type3D('o', { family: FAM, size: 1, depth }, bone); // built afresh
    expect(d.glyphs[0]!.mesh.geometry).not.toBe(geo);
    d.dispose();
  });

  test('reset() puts every glyph back at rest', () => {
    const t = new Type3D('ab', { family: FAM, size: 2 }, bone);
    const g = t.glyphs[1]!;
    g.mesh.position.set(9, 9, 9);
    g.mesh.rotation.set(1, 2, 3);
    g.mesh.scale.setScalar(5);
    t.reset();
    expect(g.mesh.position.toArray()).toEqual(g.home.toArray());
    expect(g.mesh.rotation.toArray().slice(0, 3)).toEqual([0, 0, 0]);
    expect(g.mesh.scale.toArray()).toEqual([2, 2, 2]);
    t.dispose();
  });

  test('F.display names the family Type3D is built from', () => {
    expect(F.display(100, 600)).toBe(FAM);
  });
});

// ------------------------------------------------------------------------------------------------------ materials

describe('Mat', () => {
  const close = (a: number[], b: number[]) => a.forEach((v, i) => expect(v).toBeCloseTo(b[i]!, 6));

  test('satin bone: physical, bone, roughness 0.38, clearcoat 0.25, sheen 0.3, no glow', () => {
    const m = Mat.satinBone();
    expect(m).toBeInstanceOf(THREE.MeshPhysicalMaterial);
    close(m.color.toArray(), LIN.bone);
    expect(m.roughness).toBeCloseTo(0.38, 9);
    expect(m.clearcoat).toBeCloseTo(0.25, 9);
    expect(m.sheen).toBeCloseTo(0.3, 9);
    expect(m.metalness).toBe(0);
    expect(m.emissive.getHex()).toBe(0);
  });

  test('accents: satin bone whose emissive is glow(c, level), confined to the edge in the physical shader', () => {
    for (const [c, level] of [['moss', GLOW_LEVEL], ['blood', 2]] as const) {
      const m = level === GLOW_LEVEL ? Mat.accent(c) : Mat.accent(c, level);
      expect(m).toBeInstanceOf(THREE.MeshPhysicalMaterial);
      close(m.color.toArray(), LIN.bone);
      close(m.emissive.clone().multiplyScalar(m.emissiveIntensity).toArray(), glow(c, level));
      // the rim is spliced into three's own physical shader: both anchors must still exist
      const sh = { vertexShader: THREE.ShaderLib.physical.vertexShader, fragmentShader: THREE.ShaderLib.physical.fragmentShader, uniforms: {} };
      m.onBeforeCompile(sh as any, null as any);
      expect(sh.vertexShader).toContain('vType3dN = objectNormal;');
      expect(sh.vertexShader).toContain('vType3dD = type3dDepth;');
      expect(sh.fragmentShader).toContain('float type3dK = type3dRim( vType3dN, vType3dD );');
      expect(sh.fragmentShader).toContain('totalEmissiveRadiance *= type3dK;');
      expect(sh.fragmentShader).toMatch(/#include <lights_physical_fragment>\s+material\.diffuseColor \*= 1\.0 - [\d.]+ \* type3dK;/);
      expect(m.customProgramCacheKey()).not.toBe(Mat.satinBone().customProgramCacheKey());
    }
  });
});

describe('Type3D.setSize', () => {
  const bone = new THREE.MeshBasicMaterial();

  test('a line built at one size and set to another is the line built at that size, every glyph back at rest', () => {
    const t = new Type3D('every memory', { family: FAM, size: 1 }, bone);
    t.glyphs[0]!.mesh.rotation.set(0.3, 0, 0); // posed by a scene: setSize puts it back at rest
    t.glyphs[1]!.mesh.position.set(9, 9, 9);
    t.setSize(2.5);
    const ref = new Type3D('every memory', { family: FAM, size: 2.5 }, bone);
    expect(t.size).toBe(2.5);
    expect(t.width).toBeCloseTo(ref.width, 9);
    t.glyphs.forEach((g, k) => {
      const r = ref.glyphs[k]!;
      expect(g.x).toBeCloseTo(r.x, 9);
      expect(g.w).toBeCloseTo(r.w, 9);
      for (const a of ['x', 'y', 'z'] as const) {
        expect(g.home[a]).toBeCloseTo(r.home[a], 9);
        expect(g.mesh.position[a]).toBe(g.home[a]);
        expect(g.mesh.scale[a]).toBe(2.5);
        expect(g.mesh.rotation[a]).toBe(0);
      }
    });
    t.setSize(1); // and back
    const one = new Type3D('every memory', { family: FAM, size: 1 }, bone);
    t.glyphs.forEach((g, k) => expect(g.home.x).toBeCloseTo(one.glyphs[k]!.home.x, 9));
    for (const x of [t, ref, one]) x.dispose();
  });

  test('from size 1 its rest is exactly each home times the size (as a scene scaled its glyphs by hand)', () => {
    const t = new Type3D('3f9a1c2 remember', { family: F.mono(400), size: 1 }, bone);
    const homes = t.glyphs.map((g) => g.home.clone());
    t.setSize(0.0123);
    t.glyphs.forEach((g, k) => {
      expect(g.mesh.position.toArray()).toEqual(homes[k]!.clone().multiplyScalar(0.0123).toArray());
      expect(g.mesh.scale.x).toBe(0.0123);
    });
    t.dispose();
  });

  test('a size that is not a positive number is an error', () => {
    const t = new Type3D('ab', { family: FAM, size: 1 }, bone);
    for (const s of [0, -1, NaN, Infinity]) expect(() => t.setSize(s)).toThrow();
    t.dispose();
  });
});
