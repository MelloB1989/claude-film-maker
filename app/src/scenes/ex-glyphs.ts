// The glyphs of scene `ex`: a signed-distance atlas of JetBrains Mono and two instanced draws of glyph cells that read
// it. The cloud (about 40,000 cells, every numeral of ex-cloud.ts) animates on the GPU, a pure function of the song
// time and a few uniforms. The actors (the cards' letters and the terminal's fatal line, a few hundred at most) are
// posed on the CPU each frame.
//
// The atlas. Each glyph is set by Canvas2D (the film's loaded FontFace) into a cell of 1.0 x 1.5 em, its origin (left
// end of the advance, on the baseline) 0.2 em from the cell's left and 0.4 em above its bottom, and turned into a
// signed distance field (Felzenszwalb and Huttenlocher's exact Euclidean transform of the inside and the outside, the
// anti-aliased edge taken as a sub-pixel offset). 0.5 is the outline. So a cell stays crisp in a close-up, mips down for
// the far numerals, and two glyphs can morph by mixing their fields.
//
// A cell draws one of three ways (its mode):
// - plain: one glyph;
// - flip: a split-flap board's flap, glyph A turning over to B with progress p (0..1). The top half of A falls toward
//   the viewer about the hinge, foreshortened and darkening as it turns, and uncovers B's top; past half way B's
//   bottom comes down over A's. A tile, the board's card, shows behind a flipping cell, split at the hinge;
// - morph: A's field mixed into B's by k, so a letter's shape melts into a numeral's.
// Ink and tile are drawn premultiplied and write depth (the depth of field reads it); empty pixels are discarded.
import * as THREE from 'three';
import { font } from '../engine/type';
import { HEX } from '../engine/palette';

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
/** What a cloud cell draws (em about the origin): a digit's ink (JetBrains Mono: 0.08–0.52 by -0.01–0.74), the
 * tile and the outline's anti-aliasing, all inside it. */
const QUAD = { x0: -0.02, y0: -0.17, w: 0.64, h: 1.06 } as const;
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

export class Atlas {
  texture: THREE.DataTexture;
  readonly cols = COLS;
  readonly rows: number;
  /** Atlas index of each character. */
  private index = new Map<string, number>();

  /** `chars`: what it holds, in order (so "0123456789" first puts digit d at index d). */
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
    if (g === undefined) throw new Error(`ex-glyphs: the atlas has no ${JSON.stringify(ch)}`);
    return g;
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

/** The fragment shader both draws share: a cell's glyph(s) from the atlas, plain, flipping or morphing, over a tile. */
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

const VERT_HEAD = /* glsl */ `
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

// ------------------------------------------------------------------------------------------------ the cloud

/**
 * The cloud's vertex shader. Each instance is one cell of a numeral, at rest in the lattice; time moves it:
 * - its numeral breathes a fraction of a millimetre;
 * - shockwaves (a stamp's impact, a card's landing) push it out from their centre as their front passes;
 * - pings (a query) brighten it as their shell passes;
 * - light: a key from the upper left across the spheroid, its loose edge falling away, a band sweeping through;
 * - a flip schedule (the overwrite): a split-flap run landing on a beat, a tile behind the numeral while it flips;
 * - the collapse: after the drop (and its delay) its numeral falls under gravity, sliding to its slot on the line,
 *   squeezes into the slot's cell as it lands and goes.
 */
const CLOUD_VERT = /* glsl */ `${VERT_HEAD}
in vec4 aPos;  // the cell's origin (left end, baseline) at rest; its glyph (-1 blank)
in vec4 aNum;  // numeral id, strength, cell index (0..6), flags (1: region, 2: a Berlin slot)
in vec4 aFlip; // from glyph, to glyph, landing time (0: none), flaps (0: this cell stays)
in vec4 aFall; // line slot (0..1), the drop's delay, ellipsoidal radius, seed
uniform float uTime, uEm, uAdv, uStep;
uniform vec4 uShock[4];  // centre, time
uniform vec4 uShockK[4]; // amplitude (m), speed (m/s), width (m), decay (1/s)
uniform vec4 uPing[2];   // origin, time
uniform vec4 uPingK;     // speed (m/s), width (m), strength, life (s)
uniform vec4 uLit;       // numeral id lit (why?), level
uniform vec4 uKey;       // toward the key light, its share of the strength
uniform vec4 uSweep;     // a band's normal (unit), its offset along it (m)
uniform vec4 uSweepK;    // half-width (m), level
uniform vec4 uLine;      // the line's first cell origin (x, y, z), cell pitch
uniform vec4 uCollapse;  // drop time, gravity (m/s²), cells on the line, fade (s)
uniform vec4 uRegion;    // the region's lift, Berlin's landing time, breath (m), extra
uniform vec4 uFade;      // the whole cloud's strength, the far side's dimming, unused, unused
uniform vec4 uFocus;     // the focus distance (m down the view axis), dimming from, to (m off it), level there
uniform vec3 uSpheroid;

const vec4 QUAD = vec4(${f(QUAD.x0)}, ${f(QUAD.y0)}, ${f(QUAD.w)}, ${f(QUAD.h)}); // x0, y0, w, h (em)

float h1(float x) { return fract(sin(x * 127.1 + 311.7) * 43758.5453); }

void main() {
  float t = uTime;
  float id = aNum.x, bright = aNum.y, cellI = aNum.z, flags = aNum.w, seed = aFall.w;
  // the numeral's centre (its cells share it, so it moves as one)
  vec3 c = aPos.xyz + vec3((3.5 - cellI) * uAdv, ${f(HINGE)} * uEm, 0.0);
  vec3 move = uRegion.z * vec3(sin(t * 0.83 + seed * 6.283), sin(t * 0.61 + seed * 4.1), sin(t * 0.47 + seed * 2.9));
  for (int s = 0; s < 4; s++) {
    vec4 sh = uShock[s], sk = uShockK[s];
    float dt = t - sh.w;
    if (sk.x == 0.0 || dt <= 0.0) continue;
    vec3 d = c - sh.xyz;
    float r = length(d), x = (r - sk.y * dt) / sk.z;
    move += sk.x * exp(-dt * sk.w) * exp(-x * x) * d / max(r, 1e-4);
  }
  // light
  vec3 n = normalize(c / (uSpheroid * uSpheroid) + 1e-6);
  float rn = aFall.z;
  float lit = pow(max(dot(n, uKey.xyz), 0.0), 1.2);
  float edge = 1.0 - smoothstep(0.95, 1.08, rn);
  // within the spec's 25–60% of bone: where in the band is the key light's share (uKey.w) and the numeral's own
  float own = clamp((bright - 0.25) / 0.35, 0.0, 1.0);
  float b = (0.25 + 0.35 * mix(own, lit, uKey.w)) * mix(0.45, 1.0, edge);
  float band = dot(c, uSweep.xyz) - uSweep.w;
  b += uSweepK.y * exp(-band * band / (uSweepK.x * uSweepK.x)) * edge;
  for (int s = 0; s < 2; s++) {
    vec4 pg = uPing[s];
    float dt = t - pg.w;
    if (dt <= 0.0 || dt > uPingK.w) continue;
    float r = (length(c - pg.xyz) - uPingK.x * dt) / uPingK.y;
    b += uPingK.z * exp(-r * r) * (1.0 - dt / uPingK.w);
  }
  b *= mix(1.0, 0.55, uFade.y * smoothstep(0.0, -uSpheroid.z, c.z));
  // what is far off the focus plane steps back (its blur already spreads it thin; this keeps the haze quiet)
  float vz = -(viewMatrix * modelMatrix * vec4(c + move, 1.0)).z;
  b *= mix(1.0, uFocus.w, smoothstep(uFocus.y, uFocus.z, abs(vz - uFocus.x)));
  bool region = mod(flags, 2.0) > 0.5;
  bool berlin = flags > 1.5;
  if (region) b = mix(b, max(b, 0.64), uRegion.x) + uRegion.w;
  if (abs(id - uLit.x) < 0.5) b = mix(b, 1.0, uLit.y);
  // the glyph: at rest, or a flap of the overwrite (digits are the atlas's first ten glyphs)
  vec4 glyph = vec4(aPos.w, -1.0, 0.0, 0.0);
  float tile = 0.0;
  if (aFlip.z > 0.0) {
    // each cell's own flap speed (a board's motors differ), so the flaps are out of phase; the last lands on the beat
    // (ex-cloud.ts flapAt is the same run on the CPU)
    float flapLen = uStep * (0.72 + 0.56 * h1(seed * 7.7 + cellI * 1.37));
    float land = aFlip.z, steps = aFlip.w, t0 = land - steps * flapLen;
    if (t >= land) glyph.x = aFlip.y;
    else if (steps > 0.5 && t >= t0) {
      float u = (t - t0) / flapLen, k = min(steps - 1.0, floor(u)), p = u - k;
      float digit = aFlip.x >= 0.0 && aFlip.x < 9.5 && aFlip.y >= 0.0 && aFlip.y < 9.5 ? 1.0 : 0.0;
      float between = floor(h1(seed * 13.7 + cellI * 3.1 + k * 7.31) * 10.0);
      float next = floor(h1(seed * 13.7 + cellI * 3.1 + (k + 1.0) * 7.31) * 10.0);
      float fromG = k < 0.5 ? aFlip.x : (digit > 0.5 ? between : aFlip.x);
      float toG = k > steps - 1.5 ? aFlip.y : (digit > 0.5 ? next : aFlip.y);
      glyph = vec4(fromG, toG, p * p, 1.0); // the flap falls under gravity: slow off the hinge, hard onto the stop
    }
    float near = land - 0.42;
    tile = smoothstep(near - 0.06, near + 0.04, t) * (1.0 - smoothstep(land + 0.05, land + 0.5, t));
    b = mix(b, max(b, 0.9), tile);
  }
  float alpha = uFade.x;
  if (berlin) alpha *= step(uRegion.y, t);
  // the collapse: a breath of anticipation first (the whole cloud lifts a few millimetres and hangs), then the drop
  vec3 cNow = c + move;
  float pre = clamp((t - (uCollapse.x - 0.24)) / 0.24, 0.0, 1.0);
  cNow.y += 0.006 * sin(3.14159265 * pre) * step(t, uCollapse.x);
  float squeeze = 0.0;
  float dt = t - (uCollapse.x + aFall.y);
  if (dt > 0.0) {
    // the whole sculpture drops at once (gravity is the same for all), keeping its shape; each numeral swings to its
    // slot only late in its fall, so the cloud's bottom drains into the line first, like an hourglass (ex-cloud.ts fall)
    float g = uCollapse.y;
    float h = max(c.y - uLine.y - ${f(HINGE)} * uEm, 1e-4);
    float dur = sqrt(2.0 * h / g);
    float fallen = min(0.5 * g * dt * dt, h);
    float u = min(dt / dur, 1.0), side = smoothstep(0.42, 1.0, u);
    float slotX = uLine.x + (floor(aFall.x * (uCollapse.z - 1.0) + 0.5) + 0.5) * uLine.w;
    cNow = vec3(mix(cNow.x, slotX, side), c.y - fallen, mix(cNow.z, uLine.z, side));
    squeeze = smoothstep(0.82, 1.0, u);
    alpha *= 1.0 - smoothstep(dur, dur + uCollapse.w, dt);
    b *= mix(1.0, 1.35, squeeze);
    tile = 0.0;
  }
  float cellX = mix((cellI - 3.5) * uAdv, -0.5 * uAdv, squeeze);
  vec3 origin = vec3(cNow.x + cellX, cNow.y - ${f(HINGE)} * uEm, cNow.z);
  // the quad covers a numeral glyph's ink and its flip tile, not the atlas cell's full reach (2.5x the pixels)
  vec2 e = QUAD.xy + corner * QUAD.zw;
  vec3 world = origin + vec3(e.x * (1.0 - 0.35 * squeeze), e.y * (1.0 - 0.2 * squeeze), 0.0) * uEm;
  vUv = (e - vec2(CELL_X0, CELL_Y0)) / vec2(CELL_W, CELL_H);
  vGlyph = glyph;
  vCol = vec4(boneAt(b), alpha);
  vTile = vec2(tile * alpha, 1.0);
  if (alpha <= 0.0 || (glyph.x < -0.5 && glyph.y < -0.5 && tile <= 0.0)) {
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0); // nothing to draw: outside the clip volume
    return;
  }
  gl_Position = projectionMatrix * viewMatrix * modelMatrix * vec4(world, 1.0);
}`;

/** A quad of the cell's four corners (0..1), two triangles. */
function quad(g: THREE.InstancedBufferGeometry) {
  g.setAttribute('corner', new THREE.BufferAttribute(new Float32Array([0, 0, 1, 0, 1, 1, 0, 1]), 2));
  g.setIndex([0, 1, 2, 0, 2, 3]);
}

function material(vert: string, atlas: Atlas, uniforms: Record<string, THREE.IUniform>) {
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

/** One cell of the cloud, as the cloud's attributes hold it. */
export interface CloudCell {
  /** Origin (left end, baseline) and glyph (-1 blank). */
  x: number; y: number; z: number; glyph: number;
  id: number; bright: number; cell: number; flags: number;
  /** The overwrite: from and to glyphs, the beat the last flap lands on (0: never), how many flaps (0: stays). */
  flipFrom: number; flipTo: number; land: number; steps: number;
  /** Its slot on the line (0..1), the drop's delay (s), its ellipsoidal radius, and a seed in 0..1 (float-safe). */
  slot: number; delay: number; rn: number; seed: number;
}

/** The uniforms the scene drives each frame. */
export function cloudUniforms() {
  const v4 = (x = 0, y = 0, z = 0, w = 0) => new THREE.Vector4(x, y, z, w);
  return {
    uTime: { value: 0 }, uEm: { value: 0.0075 }, uAdv: { value: 0.0045 }, uStep: { value: 0.07 },
    uShock: { value: [v4(), v4(), v4(), v4()] }, uShockK: { value: [v4(), v4(), v4(), v4()] },
    uPing: { value: [v4(0, 0, 0, 1e9), v4(0, 0, 0, 1e9)] }, uPingK: { value: v4(0.5, 0.03, 0, 1) },
    uLit: { value: v4(-1, 0) },
    uKey: { value: v4(0, 0, 1, 0) },
    uSweep: { value: v4(1, 0, 0, 99) }, uSweepK: { value: v4(0.05, 0) },
    uLine: { value: v4() }, uCollapse: { value: v4(1e9, 6, 63, 0.05) },
    uRegion: { value: v4(0, -1e9, 0, 0) },
    uFade: { value: v4(1, 0) },
    uFocus: { value: v4(1, 1e3, 2e3, 1) },
    uSpheroid: { value: new THREE.Vector3(0.5, 0.32, 0.32) },
  };
}
export type CloudUniforms = ReturnType<typeof cloudUniforms>;

export class CloudField {
  mesh: THREE.Mesh;
  u: CloudUniforms;
  private geo: THREE.InstancedBufferGeometry;
  private mat: THREE.RawShaderMaterial;

  constructor(cells: readonly CloudCell[], atlas: Atlas) {
    const n = cells.length;
    const pos = new Float32Array(n * 4), num = new Float32Array(n * 4), flip = new Float32Array(n * 4), fall = new Float32Array(n * 4);
    cells.forEach((c, i) => {
      pos.set([c.x, c.y, c.z, c.glyph], i * 4);
      num.set([c.id, c.bright, c.cell, c.flags], i * 4);
      flip.set([c.flipFrom, c.flipTo, c.land, c.steps], i * 4);
      fall.set([c.slot, c.delay, c.rn, c.seed], i * 4);
    });
    this.geo = new THREE.InstancedBufferGeometry();
    quad(this.geo);
    this.geo.setAttribute('aPos', new THREE.InstancedBufferAttribute(pos, 4));
    this.geo.setAttribute('aNum', new THREE.InstancedBufferAttribute(num, 4));
    this.geo.setAttribute('aFlip', new THREE.InstancedBufferAttribute(flip, 4));
    this.geo.setAttribute('aFall', new THREE.InstancedBufferAttribute(fall, 4));
    this.geo.instanceCount = n;
    this.u = cloudUniforms();
    this.mat = material(CLOUD_VERT, atlas, this.u);
    this.mesh = new THREE.Mesh(this.geo, this.mat);
    this.mesh.frustumCulled = false;
  }

  dispose() {
    this.geo.dispose();
    this.mat.dispose();
  }
}

// ------------------------------------------------------------------------------------------------ the actors

/** The actors' vertex shader: each instance posed on the CPU (origin, the em's two axes, glyph state, colour). */
const ACTOR_VERT = /* glsl */ `${VERT_HEAD}
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

export interface ActorPose {
  origin: THREE.Vector3;
  /** One em along the line, and one em up (world). */
  right: THREE.Vector3;
  up: THREE.Vector3;
  /** A, B (atlas indices, -1 blank), progress, mode (0 plain, 1 flip, 2 morph). */
  glyph: [number, number, number, number];
  /** Linear colour (may be past 1 for a glow) and opacity. */
  color: [number, number, number, number];
  /** Tile alpha and brightness. */
  tile?: [number, number];
}

/** Glyph cells posed on the CPU every frame (cleared by begin(), uploaded by end()). */
export class Actors {
  mesh: THREE.Mesh;
  private geo: THREE.InstancedBufferGeometry;
  private mat: THREE.RawShaderMaterial;
  private bufs: Record<string, Float32Array> = {};
  private attrs: THREE.InstancedBufferAttribute[] = [];
  private n = 0;

  constructor(readonly capacity: number, atlas: Atlas) {
    this.geo = new THREE.InstancedBufferGeometry();
    quad(this.geo);
    for (const [name, size] of [['aOrigin', 3], ['aRight', 3], ['aUp', 3], ['aGlyph', 4], ['aColor', 4], ['aTileIn', 2]] as const) {
      const b = new Float32Array(capacity * size);
      const a = new THREE.InstancedBufferAttribute(b, size);
      a.setUsage(THREE.DynamicDrawUsage);
      this.geo.setAttribute(name, a);
      this.bufs[name] = b;
      this.attrs.push(a);
    }
    this.geo.instanceCount = 0;
    this.mat = material(ACTOR_VERT, atlas, {});
    this.mesh = new THREE.Mesh(this.geo, this.mat);
    this.mesh.frustumCulled = false;
  }

  get count() {
    return this.n;
  }

  begin() {
    this.n = 0;
  }

  add(p: ActorPose) {
    if (this.n >= this.capacity) throw new Error(`ex-glyphs: more than ${this.capacity} actors`);
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
