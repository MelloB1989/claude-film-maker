// The engine's glyphs (glyphs.ts): the signed-distance atlas's transform, the split-flap's schedule, and the instanced
// glyph cells (posed on the CPU, or by a scene's own vertex shader on the shared fragment shader). The atlas itself
// draws with Canvas2D, which bun lacks: its draws take a stand-in with the atlas's texture and grid.
import { describe, expect, test } from 'bun:test';
import * as THREE from 'three';
import { CELL, GLYPH_VERT_HEAD, GlyphActors, HINGE, edt, flapAt, flapDigit, glyphMaterial, glyphQuad, sdfOf, type GlyphPose } from './glyphs';

const atlas = { texture: new THREE.DataTexture(new Uint8Array(4), 2, 2), cols: 16, rows: 3 };
const pose = (x: number, o: Partial<GlyphPose> = {}): GlyphPose => ({
  origin: new THREE.Vector3(x, 2, 3), right: new THREE.Vector3(0.01, 0, 0), up: new THREE.Vector3(0, 0.01, 0),
  glyph: [4, -1, 0, 0], color: [0.5, 0.6, 0.7, 1], ...o,
});

describe('glyphs: the distance field', () => {
  test('the exact transform gives squared distances to the nearest feature', () => {
    const w = 7, h = 5, g = new Float64Array(w * h).fill(1e20);
    g[2 * w + 3] = 0;
    edt(g, w, h);
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) expect(g[y * w + x]).toBe((x - 3) ** 2 + (y - 2) ** 2);
  });

  test('a filled square reads above 0.5 inside, below outside, and 0.5 on its anti-aliased edge', () => {
    const w = 40, h = 40, cover = new Float32Array(w * h);
    for (let y = 10; y < 30; y++) for (let x = 10; x < 30; x++) cover[y * w + x] = 1;
    for (let y = 10; y < 30; y++) cover[y * w + 30] = 0.5; // a half-covered column on the right edge
    const f = sdfOf(cover, w, h, 8);
    expect(f[20 * w + 20]!).toBeCloseTo(1, 6); // 10 px in: past the spread
    expect(f[20 * w + 2]!).toBeCloseTo(0, 6); // 8 px out
    expect(f[20 * w + 30]!).toBeCloseTo(0.5, 2); // the half-covered pixel holds the outline
    expect(f[20 * w + 12]!).toBeGreaterThan(0.5);
    expect(f[20 * w + 7]!).toBeLessThan(0.5);
  });

  test('a cell holds a mono glyph about its origin, and the flap hinges at half a digit\'s height', () => {
    expect(CELL).toEqual({ x0: -0.2, y0: -0.4, w: 1.0, h: 1.5 });
    expect(HINGE).toBe(0.365);
  });
});

describe('glyphs: the split-flap', () => {
  test('a run lands its last flap exactly on its beat', () => {
    const land = 10.808, step = 0.07;
    expect(flapAt(land - 3 * step - 1e-6, land, 3, step).k).toBe(-1);
    expect(flapAt(land - 3 * step, land, 3, step)).toEqual({ k: 0, p: 0 });
    const last = flapAt(land - 1e-6, land, 3, step);
    expect(last.k).toBe(2);
    expect(last.p).toBeCloseTo(1, 4);
    expect(flapAt(land, land, 3, step).k).toBe(3);
    expect(flapAt(land - 1, land, 0, step)).toEqual({ k: -1, p: 0 }); // no flaps: never under way
  });

  test('the digits between never show the value it leaves or the one it lands on, seeded', () => {
    for (let k = 0; k < 50; k++) {
      const d = flapDigit(k * 13, k, '4', '7');
      expect(d).not.toBe('4');
      expect(d).not.toBe('7');
      expect(d).toMatch(/^\d$/);
      expect(flapDigit(k * 13, k, '4', '7')).toBe(d);
    }
  });
});

describe('glyphs: the cells', () => {
  test('a quad of the cell\'s four corners, two triangles', () => {
    const g = new THREE.InstancedBufferGeometry();
    glyphQuad(g);
    expect(Array.from(g.getAttribute('corner').array)).toEqual([0, 0, 1, 0, 1, 1, 0, 1]);
    expect(Array.from(g.getIndex()!.array)).toEqual([0, 1, 2, 0, 2, 3]);
  });

  test('a scene\'s own vertex shader draws on the shared fragment shader: premultiplied, writing depth', () => {
    // what a vertex shader built on GLYPH_VERT_HEAD hands the fragment shader
    for (const decl of ['in vec2 corner;', 'out vec2 vUv;', 'out vec4 vGlyph;', 'out vec4 vCol;', 'out vec2 vTile;', 'vec3 boneAt(float b)']) {
      expect(GLYPH_VERT_HEAD).toContain(decl);
    }
    const vert = `${GLYPH_VERT_HEAD}\nuniform float uMine;\nvoid main() { vUv = corner; gl_Position = vec4(corner, 0.0, 1.0); }`;
    const m = glyphMaterial(vert, atlas, { uMine: { value: 2 } });
    expect(m.vertexShader).toBe(vert);
    for (const decl of ['in vec2 vUv;', 'in vec4 vGlyph;', 'in vec4 vCol;', 'in vec2 vTile;', 'uniform sampler2D uAtlas;']) expect(m.fragmentShader).toContain(decl);
    expect(m.glslVersion).toBe(THREE.GLSL3);
    expect(m.uniforms.uAtlas!.value).toBe(atlas.texture);
    expect((m.uniforms.uGrid!.value as THREE.Vector2).toArray()).toEqual([16, 3]);
    expect(m.uniforms.uMine!.value).toBe(2);
    expect([m.blending, m.blendSrc, m.blendDst, m.blendSrcAlpha, m.blendDstAlpha]).toEqual([
      THREE.CustomBlending, THREE.OneFactor, THREE.OneMinusSrcAlphaFactor, THREE.OneFactor, THREE.OneMinusSrcAlphaFactor,
    ]);
    expect([m.transparent, m.depthWrite, m.depthTest, m.side]).toEqual([true, true, true, THREE.DoubleSide]);
    // every draw shares the one fragment shader
    expect(glyphMaterial(vert, atlas, {}).fragmentShader).toBe(m.fragmentShader);
    m.dispose();
  });

  test('actors: posed each frame between begin() and end(), as many as were added, hidden when none', () => {
    const a = new GlyphActors(3, atlas);
    a.begin();
    a.add(pose(1));
    a.add(pose(2, { glyph: [1, 7, 0.25, 1], tile: [0.5, 0.9] }));
    a.end();
    const geo = a.mesh.geometry as THREE.InstancedBufferGeometry;
    expect(a.count).toBe(2);
    expect(geo.instanceCount).toBe(2);
    expect(a.mesh.visible).toBe(true);
    const buf = (n: string) => Array.from(geo.getAttribute(n).array as Float32Array);
    expect(buf('aOrigin').slice(0, 6)).toEqual([1, 2, 3, 2, 2, 3]);
    expect(buf('aGlyph').slice(4, 8)).toEqual([1, 7, 0.25, 1]);
    expect(buf('aColor').slice(0, 4).map((x) => Math.round(x * 100) / 100)).toEqual([0.5, 0.6, 0.7, 1]);
    expect(buf('aTileIn').slice(0, 4).map((x) => Math.round(x * 100) / 100)).toEqual([0, 1, 0.5, 0.9]); // no tile: none
    a.begin();
    a.end();
    expect(a.count).toBe(0);
    expect(geo.instanceCount).toBe(0);
    expect(a.mesh.visible).toBe(false);
    a.dispose();
  });

  test('actors: one past capacity is an error, never a silently dropped glyph', () => {
    const a = new GlyphActors(1, atlas);
    a.begin();
    a.add(pose(0));
    expect(() => a.add(pose(1))).toThrow(/more than 1/);
    a.dispose();
  });
});
