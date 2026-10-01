// Glyphs as GPU cells: a signed-distance atlas of a font's characters, and instanced quads that each draw one of them
// (scene `ex`'s float cloud and fatal line; `merkle`'s leaves, `proof`'s digit drums and `graph`'s labels). Thousands
// of glyphs in one draw, crisp in a close-up and mipped for the far ones, each able to flip like a split-flap board or
// morph into another.
//
// The atlas (GlyphAtlas). Each glyph is set by Canvas2D (the film's loaded FontFace) into a cell of 1.0 x 1.5 em (CELL),
// its origin (left end of the advance, on the baseline) 0.2 em from the cell's left and 0.4 em above its bottom, and
// turned into a signed distance field (Felzenszwalb and Huttenlocher's exact Euclidean transform of the inside and the
// outside, the anti-aliased edge taken as a sub-pixel offset). 0.5 is the outline. So a cell stays crisp in a close-up,
// mips down for the far numerals, and two glyphs can morph by mixing their fields. The cell is sized for JetBrains Mono
// (every advance 0.6 em): a glyph wider than 0.8 em from its origin, or reaching 1.1 em above the baseline or 0.4 below
// it, is cut at the cell's edge.
//
// A cell draws one of three ways (its mode):
// - plain: one glyph;
// - flip: a split-flap board's flap, glyph A turning over to B with progress p (0..1). The top half of A falls toward
//   the viewer about the hinge (HINGE: half a digit's height), foreshortened and darkening as it turns, and uncovers B's
//   top; past half way B's bottom comes down over A's. A tile, the board's card, shows behind a flipping cell, split at
//   the hinge. flapAt schedules a run of flaps to land on a beat, flapDigit the digits between;
// - morph: A's field mixed into B's by k, so a letter's shape melts into a numeral's.
// Ink and tile are drawn premultiplied and write depth (the depth of field reads it); empty pixels are discarded.
//
// Two ways to pose cells, both on the one fragment shader:
// - GlyphActors: a few hundred cells posed on the CPU each frame (begin, add, end): an origin, the em's two axes in the
//   world, the glyph state and a linear colour (past 1 for a glow);
// - a field of thousands animated on the GPU, a pure function of time and a few uniforms (ex's cloud, ex-glyphs.ts): an
//   InstancedBufferGeometry with glyphQuad's corners and the scene's own per-instance attributes, drawn by
//   glyphMaterial with a vertex shader that starts with GLYPH_VERT_HEAD and sets gl_Position and the four outputs the
//   fragment shader reads: vUv (0..1 across the atlas cell, y up), vGlyph (A, B, progress, mode: 0 plain, 1 flip,
//   2 morph; glyphs are atlas indices, -1 blank), vCol (linear colour, opacity) and vTile (tile alpha, brightness).
import * as THREE from 'three';
import { font } from './type';
import { HEX } from './palette';
import { hash } from './util';

// ------------------------------------------------------------------------------------------------ the atlas

/** Atlas px per em, and how far (px) the distance field reaches either side of an outline. */
const EM_PX = 96;
const SPREAD = 10;
/** A cell (em, y up) about the glyph's origin: x from X0 over W, y from Y0 over H. */
export const CELL = { x0: -0.2, y0: -0.4, w: 1.0, h: 1.5 } as const;
const CELL_W = Math.round(CELL.w * EM_PX), CELL_H = Math.round(CELL.h * EM_PX);
/** The split-flap's hinge (em above the baseline: half a digit's height) and its tile (em, about the origin). */
export const HINGE = 0.365;
const TILE = { x0: 0.02, x1: 0.58, y0: -0.13, y1: 0.86, r: 0.07 } as const;
const COLS = 16;
const INF = 1e20;

/** One row or column of Felzenszwalb–Huttenlocher: f (squared distances to features) in, d (the transform) out. */
function edt1(f: Float64Array, d: Float64Array, v: Int32Array, z: Float64Array, n: number) {
  let k = 0;
  v[0] = 0;
  z[0] = -INF;
  z[1] = INF;
  for (let q = 1; q < n; q++) {
    let r = v[k]!;
    let s = (f[q]! + q * q - (f[r]! + r * r)) / (2 * (q - r));
    while (s <= z[k]!) {
      k--;
      r = v[k]!;
      s = (f[q]! + q * q - (f[r]! + r * r)) / (2 * (q - r));
    }
    k++;
    v[k] = q;
    z[k] = s;
    z[k + 1] = INF;
  }
  k = 0;
  for (let q = 0; q < n; q++) {
    while (z[k + 1]! < q) k++;
    const r = v[k]!;
    d[q] = (q - r) * (q - r) + f[r]!;
  }
}

/** Squared Euclidean distance transform of a w x h grid (0 on the features, INF elsewhere), in place. */
export function edt(grid: Float64Array, w: number, h: number) {
  const n = Math.max(w, h);
  const f = new Float64Array(n), d = new Float64Array(n), v = new Int32Array(n), z = new Float64Array(n + 1);
  for (let x = 0; x < w; x++) {
    for (let y = 0; y < h; y++) f[y] = grid[y * w + x]!;
    edt1(f, d, v, z, h);
    for (let y = 0; y < h; y++) grid[y * w + x] = d[y]!;
  }
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) f[x] = grid[y * w + x]!;
    edt1(f, d, v, z, w);
    for (let x = 0; x < w; x++) grid[y * w + x] = d[x]!;
  }
}

/**
 * A signed distance field from coverage (0..1, row-major): 0.5 on the outline, rising inside, reaching 0 and 1 `spread`
 * px out and in. A partly covered pixel holds the outline at its coverage (the anti-aliased edge as a sub-pixel offset).
 */
export function sdfOf(cover: Float32Array, w: number, h: number, spread = SPREAD): Float32Array {
  const outer = new Float64Array(w * h), inner = new Float64Array(w * h);
  for (let i = 0; i < w * h; i++) {
    const a = cover[i]!;
    if (a >= 1) (outer[i] = 0), (inner[i] = INF);
    else if (a <= 0) (outer[i] = INF), (inner[i] = 0);
    else {
      const e = 0.5 - a;
      outer[i] = e > 0 ? e * e : 0;
      inner[i] = e < 0 ? e * e : 0;
    }
  }
  edt(outer, w, h);
  edt(inner, w, h);
  const out = new Float32Array(w * h);
  for (let i = 0; i < w * h; i++) {
    const dist = Math.sqrt(outer[i]!) - Math.sqrt(inner[i]!); // + outside
    out[i] = Math.min(1, Math.max(0, 0.5 - dist / (2 * spread)));
  }
  return out;
}

/** What a glyph draw reads of its atlas: the texture and its grid of cells. */
export type GlyphGrid = Pick<GlyphAtlas, 'texture' | 'cols' | 'rows'>;

/**
 * A signed-distance atlas of `chars` in a font family (F.mono(400) and the like; the fonts must be loaded). Built once,
 * on the CPU (about a millisecond a glyph): build it in init() with every character the scene will draw.
 */
export class GlyphAtlas {
  texture: THREE.DataTexture;
  readonly cols = COLS;
  readonly rows: number;
  /** Atlas index of each character. */
  private index = new Map<string, number>();

  /** `chars`: what it holds, in order (so "0123456789" first puts digit d at index d); whitespace is left out. */
  constructor(chars: Iterable<string>, family: string) {
    const list = [...new Set(chars)].filter((c) => !/\s/u.test(c));
    this.rows = Math.max(1, Math.ceil(list.length / COLS));
    const W = COLS * CELL_W, Hh = this.rows * CELL_H;
    const data = new Uint8Array(W * Hh);
    const cv = document.createElement('canvas');
    cv.width = CELL_W;
    cv.height = CELL_H;
    const c = cv.getContext('2d', { willReadFrequently: true })!;
    const cover = new Float32Array(CELL_W * CELL_H);
    list.forEach((ch, g) => {
      c.clearRect(0, 0, CELL_W, CELL_H);
      c.font = font(family, EM_PX);
      c.textBaseline = 'alphabetic';
      c.fillStyle = '#fff';
      c.fillText(ch, -CELL.x0 * EM_PX, (CELL.y0 + CELL.h) * EM_PX);
      const px = c.getImageData(0, 0, CELL_W, CELL_H).data;
      for (let i = 0; i < CELL_W * CELL_H; i++) cover[i] = px[i * 4 + 3]! / 255;
      const f = sdfOf(cover, CELL_W, CELL_H);
      const cx = (g % COLS) * CELL_W, cy = Math.floor(g / COLS) * CELL_H;
      // texture rows run up (v = 0 at the bottom): the cell's top canvas row is its top atlas row
      for (let y = 0; y < CELL_H; y++) {
        const row = (cy + CELL_H - 1 - y) * W + cx;
        for (let x = 0; x < CELL_W; x++) data[row + x] = Math.round(255 * f[y * CELL_W + x]!);
      }
      this.index.set(ch, g);
    });
    this.texture = new THREE.DataTexture(data, W, Hh, THREE.RedFormat, THREE.UnsignedByteType);
    this.texture.unpackAlignment = 1;
    this.texture.generateMipmaps = true;
    this.texture.minFilter = THREE.LinearMipmapLinearFilter;
    this.texture.magFilter = THREE.LinearFilter;
    this.texture.anisotropy = 8;
    this.texture.needsUpdate = true;
  }

  /** Atlas index of a character, -1 for a blank. A character it lacks throws (a typo fails while authoring). */
  of(ch: string): number {
    if (/\s/u.test(ch)) return -1;
    const g = this.index.get(ch);
    if (g === undefined) throw new Error(`glyphs: the atlas has no ${JSON.stringify(ch)}`);
    return g;
  }

  /** Whether it holds a character (a blank counts: it draws nothing). */
  has(ch: string): boolean {
    return /\s/u.test(ch) || this.index.has(ch);
  }

  dispose() {
    this.texture.dispose();
  }
}

// ------------------------------------------------------------------------------------------------ shaders

/** A palette hex as an sRGB vec3 literal. */
const srgb = (c: string) => {
  const n = parseInt(c.slice(1), 16);
  return `vec3(${[(n >> 16) & 255, (n >> 8) & 255, n & 255].map((x) => (x / 255).toFixed(5)).join(', ')})`;
};
const f = (x: number) => x.toFixed(5);

const COMMON = /* glsl */ `
const float CELL_X0 = ${f(CELL.x0)}, CELL_Y0 = ${f(CELL.y0)}, CELL_W = ${f(CELL.w)}, CELL_H = ${f(CELL.h)};
float lin(float c) { return c < 0.04045 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4); }
vec3 lin3(vec3 c) { return vec3(lin(c.r), lin(c.g), lin(c.b)); }
`;

/** The fragment shader every glyph draw shares: a cell's glyph(s) from the atlas, plain, flipping or morphing, over a tile. */
const FRAG = /* glsl */ `
precision highp float;
uniform sampler2D uAtlas;
uniform vec2 uGrid; // atlas columns, rows
in vec2 vUv;    // 0..1 across the cell, y up
in vec4 vGlyph; // A, B, progress, mode (0 plain, 1 flip, 2 morph)
in vec4 vCol;   // linear ink colour, opacity
in vec2 vTile;  // tile alpha, tile brightness
out vec4 fragColor;
${COMMON}
const float HINGE_EM = ${f(HINGE)};
const float HINGE = (HINGE_EM - CELL_Y0) / CELL_H; // in uv
const vec4 TILE = vec4(${f(TILE.x0)}, ${f(TILE.y0)}, ${f(TILE.x1)}, ${f(TILE.y1)}); // x0 y0 x1 y1 (em)
const float TILE_R = ${f(TILE.r)};
const vec3 TILE_S = ${srgb(HEX.ruleStrong)};
const float FIELD_PER_UV = ${f(CELL_W / (2 * SPREAD))}; // field units per uv across the cell

vec2 atlasUv(float g, vec2 uv) {
  vec2 cell = vec2(mod(g, uGrid.x), floor(g / uGrid.x));
  return (cell + clamp(uv, 0.0, 1.0)) / uGrid;
}

void main() {
  vec2 uv = vUv;
  vec2 gx = dFdx(uv), gy = dFdy(uv);
  vec2 dx = gx / uGrid, dy = gy / uGrid;
  float A = vGlyph.x, B = vGlyph.y, p = vGlyph.z, mode = vGlyph.w;
  // two samples, glyph g1 at uv1 and g2 at uv, mixed by k (plain and flip read one)
  float g1 = A, g2 = -1.0, k = 0.0;
  vec2 uv1 = uv;
  float shade = 1.0, onFlap = 0.0;
  if (mode > 1.5) { // morph
    g2 = B;
    k = p;
  } else if (mode > 0.5) { // flip
    float c = cos(3.14159265 * p);
    float up = (TILE.w - HINGE_EM) / CELL_H, down = (HINGE_EM - TILE.y) / CELL_H; // the flap's reach (uv)
    float dv = uv.y - HINGE;
    if (c > 0.0) { // A's top half falling toward the viewer
      if (dv >= 0.0 && dv < c * up) { uv1.y = HINGE + dv / c; shade = 0.4 + 0.6 * c; onFlap = 1.0; g1 = A; }
      else g1 = dv >= 0.0 ? B : A;
    } else { // B's bottom half coming down onto A's
      float cc = -c;
      if (dv < 0.0 && -dv < cc * down) { uv1.y = HINGE + dv / cc; shade = 0.4 + 0.6 * cc; onFlap = 1.0; g1 = B; }
      else g1 = dv >= 0.0 ? B : A;
    }
  }
  float s1 = g1 < -0.5 ? 0.0 : textureGrad(uAtlas, atlasUv(g1, uv1), dx, dy).r;
  float s2 = g2 < -0.5 ? 0.0 : textureGrad(uAtlas, atlasUv(g2, uv), dx, dy).r;
  float d = mix(s1, s2, k);
  // the outline's width: how far the field moves across a screen pixel
  float px = max(length(vec2(length(gx), length(gy))) * FIELD_PER_UV, 1e-4);
  float cov = smoothstep(0.5 - 0.7 * px, 0.5 + 0.7 * px, d);
  // the tile: a board's card, split at the hinge
  float tA = 0.0;
  if (vTile.x > 0.0) {
    vec2 e = vec2(CELL_X0 + uv.x * CELL_W, CELL_Y0 + uv.y * CELL_H);
    vec2 c0 = 0.5 * (TILE.xy + TILE.zw), hb = 0.5 * (TILE.zw - TILE.xy);
    vec2 q = abs(e - c0) - hb + TILE_R;
    float sd = length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - TILE_R;
    float ew = max(length(vec2(length(gx), length(gy))) * CELL_W, 1e-5); // em per pixel
    float gap = smoothstep(0.0, 1.2 * ew, abs(e.y - HINGE_EM) - 0.008);
    tA = vTile.x * clamp(0.5 - sd / ew, 0.0, 1.0) * mix(0.25, 1.0, gap);
  }
  vec3 tile = lin3(TILE_S * vTile.y) * shade;
  float inkA = cov * vCol.a;
  vec3 ink = vCol.rgb * mix(1.0, shade, onFlap);
  float a = inkA + tA * (1.0 - inkA);
  if (a < 0.006) discard;
  fragColor = vec4(ink * inkA + tile * tA * (1.0 - inkA), a);
}`;

/**
 * The head of a glyph draw's vertex shader (GLSL 3): the matrices, the quad's `corner` (0..1, from glyphQuad), the four
 * outputs the fragment shader reads (vUv, vGlyph, vCol, vTile), the cell's constants (CELL_X0, CELL_Y0, CELL_W, CELL_H),
 * the sRGB decode (lin, lin3) and boneAt(b): b of the way from ink to bone as the eye sees it, as linear light.
 */
export const GLYPH_VERT_HEAD = /* glsl */ `
precision highp float;
uniform mat4 projectionMatrix, viewMatrix, modelMatrix;
in vec2 corner;
out vec2 vUv;
out vec4 vGlyph;
out vec4 vCol;
out vec2 vTile;
${COMMON}
const vec3 INK_S = ${srgb(HEX.ink)};
const vec3 BONE_S = ${srgb(HEX.bone)};
// b of the way from ink to bone as the eye sees it (display space), as linear light
vec3 boneAt(float b) { return lin3(mix(INK_S, BONE_S, clamp(b, 0.0, 1.0))); }
`;

/** A quad of the cell's four corners (0..1), two triangles: the instanced geometry's own attribute `corner`. */
export function glyphQuad(g: THREE.InstancedBufferGeometry) {
  g.setAttribute('corner', new THREE.BufferAttribute(new Float32Array([0, 0, 1, 0, 1, 1, 0, 1]), 2));
  g.setIndex([0, 1, 2, 0, 2, 3]);
}

/**
 * A glyph draw's material: `vert` (built on GLYPH_VERT_HEAD) on the shared fragment shader, reading `atlas`, with the
 * scene's own `uniforms`. Premultiplied, writing depth, both sides.
 */
export function glyphMaterial(vert: string, atlas: GlyphGrid, uniforms: Record<string, THREE.IUniform>) {
  const m = new THREE.RawShaderMaterial({
    glslVersion: THREE.GLSL3,
    vertexShader: vert,
    fragmentShader: FRAG,
    uniforms: { uAtlas: { value: atlas.texture }, uGrid: { value: new THREE.Vector2(atlas.cols, atlas.rows) }, ...uniforms },
    transparent: true,
    depthWrite: true,
    depthTest: true,
    side: THREE.DoubleSide,
    blending: THREE.CustomBlending,
  });
  m.blendEquation = THREE.AddEquation;
  m.blendSrc = m.blendSrcAlpha = THREE.OneFactor;
  m.blendDst = m.blendDstAlpha = THREE.OneMinusSrcAlphaFactor;
  return m;
}

// ------------------------------------------------------------------------------------------------ the actors

/** The actors' vertex shader: each instance posed on the CPU (origin, the em's two axes, glyph state, colour). */
const ACTOR_VERT = /* glsl */ `${GLYPH_VERT_HEAD}
in vec3 aOrigin; // the cell's origin (left end, baseline)
in vec3 aRight;  // one em along the line
in vec3 aUp;     // one em up
in vec4 aGlyph;  // A, B, progress, mode
in vec4 aColor;  // linear colour, opacity
in vec2 aTileIn; // tile alpha, tile brightness
void main() {
  vec2 e = vec2(CELL_X0 + corner.x * CELL_W, CELL_Y0 + corner.y * CELL_H);
  vUv = corner;
  vGlyph = aGlyph;
  vCol = aColor;
  vTile = aTileIn;
  if (aColor.a <= 0.0 && aTileIn.x <= 0.0) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); return; }
  gl_Position = projectionMatrix * viewMatrix * modelMatrix * vec4(aOrigin + aRight * e.x + aUp * e.y, 1.0);
}`;

export interface GlyphPose {
  origin: THREE.Vector3;
  /** One em along the line, and one em up (world). */
  right: THREE.Vector3;
  up: THREE.Vector3;
  /** A, B (atlas indices, -1 blank), progress, mode (0 plain, 1 flip, 2 morph). */
  glyph: [number, number, number, number];
  /** Linear colour (may be past 1 for a glow) and opacity. */
  color: [number, number, number, number];
  /** Tile alpha and brightness (none by default). */
  tile?: [number, number];
}

/** Glyph cells posed on the CPU every frame (cleared by begin(), uploaded by end()), up to `capacity` of them. */
export class GlyphActors {
  mesh: THREE.Mesh;
  private geo: THREE.InstancedBufferGeometry;
  private mat: THREE.RawShaderMaterial;
  private bufs: Record<string, Float32Array> = {};
  private attrs: THREE.InstancedBufferAttribute[] = [];
  private n = 0;

  constructor(readonly capacity: number, atlas: GlyphGrid) {
    this.geo = new THREE.InstancedBufferGeometry();
    glyphQuad(this.geo);
    for (const [name, size] of [['aOrigin', 3], ['aRight', 3], ['aUp', 3], ['aGlyph', 4], ['aColor', 4], ['aTileIn', 2]] as const) {
      const b = new Float32Array(capacity * size);
      const a = new THREE.InstancedBufferAttribute(b, size);
      a.setUsage(THREE.DynamicDrawUsage);
      this.geo.setAttribute(name, a);
      this.bufs[name] = b;
      this.attrs.push(a);
    }
    this.geo.instanceCount = 0;
    this.mat = glyphMaterial(ACTOR_VERT, atlas, {});
    this.mesh = new THREE.Mesh(this.geo, this.mat);
    this.mesh.frustumCulled = false;
  }

  /** The cells added since begin(). */
  get count() {
    return this.n;
  }

  begin() {
    this.n = 0;
  }

  add(p: GlyphPose) {
    if (this.n >= this.capacity) throw new Error(`glyphs: more than ${this.capacity} actors`);
    const i = this.n++, b = this.bufs;
    b.aOrigin!.set([p.origin.x, p.origin.y, p.origin.z], i * 3);
    b.aRight!.set([p.right.x, p.right.y, p.right.z], i * 3);
    b.aUp!.set([p.up.x, p.up.y, p.up.z], i * 3);
    b.aGlyph!.set(p.glyph, i * 4);
    b.aColor!.set(p.color, i * 4);
    b.aTileIn!.set(p.tile ?? [0, 1], i * 2);
  }

  end() {
    for (const a of this.attrs) {
      a.clearUpdateRanges();
      a.addUpdateRange(0, Math.max(1, this.n) * a.itemSize);
      a.needsUpdate = true;
    }
    this.geo.instanceCount = this.n;
    this.mesh.visible = this.n > 0;
  }

  dispose() {
    this.geo.dispose();
    this.mat.dispose();
  }
}

// ------------------------------------------------------------------------------------------------ split-flap

/**
 * A split-flap run that lands at `land`: `steps` flaps of `step` seconds each, the last one coming down exactly on
 * `land`. Returns the flap under way at t (0-based) and its progress 0..1, or -1 before the run and `steps` after it.
 * (A cell flipping from A to B with that progress is GlyphPose glyph [A, B, p, 1]; ex eases it as p·p, the flap
 * falling under gravity, slow off the hinge and hard onto the stop.)
 */
export function flapAt(t: number, land: number, steps: number, step: number): { k: number; p: number } {
  const t0 = land - steps * step;
  if (steps <= 0 || t < t0) return { k: -1, p: 0 };
  if (t >= land) return { k: steps, p: 0 };
  const u = (t - t0) / step;
  const k = Math.min(steps - 1, Math.floor(u));
  return { k, p: u - k };
}

/** A digit the board shows between two values (seeded): never the value it is leaving or the one it lands on. */
export function flapDigit(seed: number, k: number, from: string, to: string): string {
  for (let a = 0; a < 6; a++) {
    const d = String(Math.floor(hash(seed, 41 + k, a) * 10));
    if (d !== from && d !== to) return d;
  }
  return String((Number(from) + 5) % 10);
}
