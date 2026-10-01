// The namespaces of scene `anywhere` (Plan 2 Task 24): `user-0001 … user-2048`, each its own memory behind its own
// boundary. One tile per namespace (the console's namespace row, lifted out of its list: a box icon and the name in
// mono on a panel tile with the panels' 1 px edge), 2,048 of them, and the doubling that makes them.
//
// The doubling (anywhere-time.ts cellOf): namespace i's index bits are dealt alternately to its column and its row, so
// each doubling copies the whole block beside itself, along x then y. A copy slides out from under the block (it
// starts at its original's place, a hair behind it, so the original hides it), lands on its sixteenth with a tight
// spring and a click, and its face and edge flash moss as it lands: namespaces added. Eleven doublings, 64 columns by
// 32 rows.
//
// All on the GPU as a pure function of the song time and a few uniforms: one instanced draw of tiles (the rounded
// rectangle, its edge and the box icon from signed distances) and one of name glyphs on the engine's atlas
// (engine/glyphs.ts, GLYPH_VERT_HEAD), each glyph moving with its tile. The field lies in its group's z = 0 plane, in
// tile px (the group's scale makes them world units), column x to the right and row y down from the first tile's top
// left corner.
import * as THREE from 'three';
import { GLYPH_VERT_HEAD, GlyphAtlas, glyphMaterial, glyphQuad } from '../engine/glyphs';
import { F } from '../engine/type';
import { HEX, LIN } from '../engine/palette';
import { glow } from '../engine/look';
import { DOUBLINGS, NAMESPACES, cellOf, copyOffset, levelOf, nsName } from './anywhere-time';

/** A tile and the grid (tile px): its size, corner radius, the gap between tiles; the icon and the name in it. */
export const TILE = {
  w: 212, h: 228, r: 20, gap: 22,
  /** The box icon: its centre's height from the tile's top, its size (the 24-unit icon drawn this many px across). */
  iconY: 84, icon: 64,
  /** The name: its em, its baseline from the tile's top. */
  em: 31, base: 180,
} as const;
export const PITCH = { x: TILE.w + TILE.gap, y: TILE.h + TILE.gap } as const;

/** How a copy slides out and lands: its spring (tight, a click), how far behind its original it starts (px). */
export const SLIDE = { freq: 6.2, damping: 0.72, behind: 6, lift: 26 } as const;
/** The moss of a landing: its peak (a glow() level on the edge; a share of it on the face) and half-life (s). */
export const FLASH = { edge: 1.45, face: 0.1, life: 0.085 } as const;

const f = (x: number) => x.toFixed(5);
const srgb = (c: string) => {
  const n = parseInt(c.slice(1), 16);
  return `vec3(${[(n >> 16) & 255, (n >> 8) & 255, n & 255].map((x) => (x / 255).toFixed(5)).join(', ')})`;
};

/**
 * The motion every tile and every glyph shares (GLSL): where tile (col, row) of doubling `level` is at uTime, its alpha,
 * its lift toward the camera, and its moss flash. The spring is motion.ts spring(), landing on uLand[level] (it first
 * reaches its place then, the overshoot after).
 */
const MOTION = /* glsl */ `
uniform float uTime;
uniform float uLand[${DOUBLINGS}];
uniform float uRise;     // the spring's rise time (s): when it first reaches 1
uniform float uFade;     // the whole field's strength
uniform float uDetail;   // 0..1: the names and icons (they go as the tiles get too small to read)
uniform vec4 uSweep;     // a band of light across the field: its centre (px along x + 0.35 y), half-width (px), level

float springAt(float t) {
  if (t <= 0.0) return 0.0;
  float w = 6.2831853 * ${f(SLIDE.freq)}, z = ${f(SLIDE.damping)};
  float a = z * w, b = w * sqrt(1.0 - z * z);
  if (a * t > 40.0) return 1.0;
  return 1.0 - exp(-a * t) * (cos(b * t) + (a / b) * sin(b * t));
}

// x, y: the tile's top-left corner (px); z: its lift; w: alpha. flash: the moss of its landing.
vec4 tileAt(vec4 cell, vec2 from, out float flash) {
  float level = cell.z;
  float s = 1.0;
  flash = 0.0;
  if (level > -0.5) {
    float land = uLand[int(level + 0.5)];
    s = springAt(uTime - (land - uRise));
    float dt = uTime - land;
    flash = dt > -0.02 ? exp2(-max(dt, 0.0) / ${f(FLASH.life)}) * smoothstep(-0.02, 0.0, dt) : 0.0;
  }
  vec2 c = cell.xy - from * (1.0 - s);
  float lift = ${f(SLIDE.lift)} * sin(3.14159265 * clamp(s, 0.0, 1.0)) - ${f(SLIDE.behind)} * (1.0 - clamp(s * 4.0, 0.0, 1.0));
  float alpha = level > -0.5 ? step(1e-4, s) : 1.0;
  return vec4(c.x * ${f(PITCH.x)}, c.y * ${f(PITCH.y)}, lift, alpha * uFade);
}

float sweepAt(vec2 px) {
  float d = (px.x + 0.35 * px.y - uSweep.x) / max(uSweep.y, 1e-3);
  return uSweep.z * exp(-d * d);
}
`;

const TILE_VERT = /* glsl */ `
precision highp float;
uniform mat4 projectionMatrix, viewMatrix, modelMatrix;
in vec2 corner;
in vec4 aCell;  // col, row, level (-1: the first), unused
in vec2 aFrom;  // back to its original (cols, rows)
out vec2 vPx;   // px in the tile, from its top left, y down
out float vFlash, vAlpha, vSweep;
${MOTION}
void main() {
  float flash;
  vec4 at = tileAt(aCell, aFrom, flash);
  vec2 px = corner * vec2(${f(TILE.w)}, ${f(TILE.h)});
  vPx = vec2(px.x, ${f(TILE.h)} - px.y);
  vFlash = flash;
  vAlpha = at.w;
  vSweep = sweepAt(at.xy + vPx);
  if (at.w <= 0.0) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); return; }
  // tile px: x right, y down from the field's top left; the group's z = 0 plane
  vec3 p = vec3(at.x + px.x, -(at.y + ${f(TILE.h)} - px.y), at.z);
  gl_Position = projectionMatrix * viewMatrix * modelMatrix * vec4(p, 1.0);
}`;

/** The box icon (lucide's Box, the console's namespace glyph family) in its 24-unit square: an outline and a Y. */
const BOX: [number, number][][] = [
  [[12, 2.2], [20.8, 7.1]], [[20.8, 7.1], [20.8, 16.9]], [[20.8, 16.9], [12, 21.8]], [[12, 21.8], [3.2, 16.9]],
  [[3.2, 16.9], [3.2, 7.1]], [[3.2, 7.1], [12, 2.2]], [[3.4, 7.2], [12, 12]], [[12, 12], [20.6, 7.2]], [[12, 12], [12, 21.8]],
];

const TILE_FRAG = /* glsl */ `
precision highp float;
in vec2 vPx;
in float vFlash, vAlpha, vSweep;
out vec4 fragColor;
uniform vec3 uFace, uEdge, uEdgeHi, uIcon, uMoss, uMossFace;
float lin(float c) { return c < 0.04045 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4); }
float sdRoundRect(vec2 p, vec2 b, float r) {
  vec2 q = abs(p) - b + r;
  return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}
float sdSeg(vec2 p, vec2 a, vec2 b) {
  vec2 pa = p - a, ba = b - a;
  return length(pa - ba * clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0));
}
void main() {
  vec2 half_ = 0.5 * vec2(${f(TILE.w)}, ${f(TILE.h)});
  float d = sdRoundRect(vPx - half_, half_, ${f(TILE.r)});
  float aa = max(fwidth(d), 1e-4);
  float cov = clamp(-d / aa, 0.0, 1.0);
  if (cov <= 0.0) discard;
  // the edge: 1.5 px, lit a little along the top as the panels' is; a landing lights it moss
  float edgeW = max(1.5, 1.2 * aa);
  float inner = clamp(-(d + edgeW) / aa, 0.0, 1.0);
  vec3 edge = mix(uEdge, uEdgeHi, 1.0 - smoothstep(0.0, 2.0 * ${f(TILE.r)}, vPx.y));
  edge = mix(edge, uMoss, clamp(vFlash, 0.0, 1.0)) + uMoss * ${f(FLASH.edge - 1)} * vFlash;
  vec3 face = uFace + uMossFace * ${f(FLASH.face)} * vFlash;
  // the box icon, its strokes 2 units of its 24
  vec2 q = (vPx - vec2(half_.x, ${f(TILE.iconY)})) / ${f(TILE.icon / 24)} + 12.0;
  float id = 1e3;
${BOX.map(([a, b]) => `  id = min(id, sdSeg(q, vec2(${f(a![0])}, ${f(a![1])}), vec2(${f(b![0])}, ${f(b![1])})));`).join('\n')}
  float ie = (id - 1.0) * ${f(TILE.icon / 24)};
  float ic = clamp(0.5 - ie / max(fwidth(ie), 1e-4), 0.0, 1.0);
  face = mix(face, uIcon, ic * 0.9 * uDetail);
  vec3 col = (face * inner + edge * (cov - inner)) / max(cov, 1e-4);
  col += vec3(vSweep) * (0.35 + 0.65 * (cov - inner) / max(cov, 1e-4));
  float a = cov * vAlpha;
  fragColor = vec4(col * a, a);
}`;

const NAME_VERT = /* glsl */ `${GLYPH_VERT_HEAD}
in vec4 aCell;  // col, row, level, character index in the name
in vec2 aFrom;
in float aGlyph;
uniform float uEm, uAdv, uX0;
${MOTION}
void main() {
  float flash;
  vec4 at = tileAt(vec4(aCell.xyz, 0.0), aFrom, flash);
  vec2 e = vec2(CELL_X0 + corner.x * CELL_W, CELL_Y0 + corner.y * CELL_H);
  vUv = corner;
  vGlyph = vec4(aGlyph, -1.0, 0.0, 0.0);
  float b = 0.86 + 0.14 * clamp(flash, 0.0, 1.0);
  vec2 org = at.xy + vec2(uX0 + aCell.w * uAdv, ${f(TILE.base)});
  b += sweepAt(org) * 0.4;
  vCol = vec4(boneAt(b), at.w * uDetail);
  vTile = vec2(0.0, 1.0);
  if (at.w * uDetail <= 0.0) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); return; }
  vec3 p = vec3(org.x + e.x * uEm, -org.y + e.y * uEm, at.z + 0.6);
  gl_Position = projectionMatrix * viewMatrix * modelMatrix * vec4(p, 1.0);
}`;

export interface FieldLook {
  t: number;
  /** The doublings' landing times (anywhere-time.ts doublings). */
  land: readonly number[];
  fade: number;
  /** The light band's centre (px, along x + 0.35 y), half-width (px) and level (0: none). */
  sweep: [number, number, number];
  /** 0..1: the names and icons. */
  detail: number;
}

export class Field {
  group = new THREE.Group();
  readonly atlas: GlyphAtlas;
  private tiles: THREE.Mesh;
  private names: THREE.Mesh;
  private tileMat: THREE.RawShaderMaterial;
  private nameMat: THREE.RawShaderMaterial;
  private geos: THREE.InstancedBufferGeometry[] = [];
  private u: Record<string, THREE.IUniform>;

  constructor() {
    const n = NAMESPACES;
    const rise = (Math.PI / 2 + Math.asin(SLIDE.damping)) / (2 * Math.PI * SLIDE.freq * Math.sqrt(1 - SLIDE.damping ** 2));
    this.u = {
      uTime: { value: 0 }, uLand: { value: new Array(DOUBLINGS).fill(1e9) }, uRise: { value: rise }, uFade: { value: 1 }, uDetail: { value: 1 },
      uSweep: { value: new THREE.Vector4(0, 1, 0, 0) },
    };
    // the tiles
    const cell = new Float32Array(n * 4), from = new Float32Array(n * 2);
    for (let i = 0; i < n; i++) {
      const c = cellOf(i), o = copyOffset(i);
      cell.set([c.x, c.y, levelOf(i), 0], 4 * i);
      from.set([o.dx, o.dy], 2 * i);
    }
    const tg = new THREE.InstancedBufferGeometry();
    glyphQuad(tg);
    tg.setAttribute('aCell', new THREE.InstancedBufferAttribute(cell, 4));
    tg.setAttribute('aFrom', new THREE.InstancedBufferAttribute(from, 2));
    tg.instanceCount = n;
    const v3 = (rgb: readonly [number, number, number]) => ({ value: new THREE.Vector3(...rgb) });
    const mix = (a: keyof typeof HEX, b: keyof typeof HEX, k: number) => {
      const pa = parseInt(HEX[a].slice(1), 16), pb = parseInt(HEX[b].slice(1), 16);
      const ch = (sh: number) => {
        const s = (((pa >> sh) & 255) * (1 - k) + ((pb >> sh) & 255) * k) / 255;
        return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
      };
      return { value: new THREE.Vector3(ch(16), ch(8), ch(0)) };
    };
    this.tileMat = new THREE.RawShaderMaterial({
      glslVersion: THREE.GLSL3, vertexShader: TILE_VERT, fragmentShader: TILE_FRAG,
      uniforms: {
        ...this.u, uFace: v3(LIN.panel), uEdge: v3(LIN.ruleStrong), uEdgeHi: mix('ruleStrong', 'bone', 0.22), uIcon: v3(LIN.boneFaint),
        uMoss: { value: new THREE.Vector3(...glow('moss', 1)) }, uMossFace: v3(LIN.mossDim),
      },
      transparent: true, depthWrite: true, side: THREE.DoubleSide, blending: THREE.CustomBlending,
    });
    this.tileMat.blendEquation = THREE.AddEquation;
    this.tileMat.blendSrc = this.tileMat.blendSrcAlpha = THREE.OneFactor;
    this.tileMat.blendDst = this.tileMat.blendDstAlpha = THREE.OneMinusSrcAlphaFactor;
    this.tiles = new THREE.Mesh(tg, this.tileMat);
    this.tiles.frustumCulled = false;
    this.geos.push(tg);

    // the names: nine glyph cells a tile, centred under the icon
    this.atlas = new GlyphAtlas('user-0123456789', F.mono(500));
    const L = nsName(0).length, adv = 0.6 * TILE.em;
    const gcell = new Float32Array(n * L * 4), gfrom = new Float32Array(n * L * 2), glyph = new Float32Array(n * L);
    for (let i = 0; i < n; i++) {
      const name = nsName(i), c = cellOf(i), o = copyOffset(i), lv = levelOf(i);
      for (let k = 0; k < L; k++) {
        const j = i * L + k;
        gcell.set([c.x, c.y, lv, k], 4 * j);
        gfrom.set([o.dx, o.dy], 2 * j);
        glyph[j] = this.atlas.of(name[k]!);
      }
    }
    const ng = new THREE.InstancedBufferGeometry();
    glyphQuad(ng);
    ng.setAttribute('aCell', new THREE.InstancedBufferAttribute(gcell, 4));
    ng.setAttribute('aFrom', new THREE.InstancedBufferAttribute(gfrom, 2));
    ng.setAttribute('aGlyph', new THREE.InstancedBufferAttribute(glyph, 1));
    ng.instanceCount = n * L;
    this.nameMat = glyphMaterial(NAME_VERT, this.atlas, { ...this.u, uEm: { value: TILE.em }, uAdv: { value: adv }, uX0: { value: (TILE.w - L * adv) / 2 } });
    this.names = new THREE.Mesh(ng, this.nameMat);
    this.names.frustumCulled = false;
    this.names.renderOrder = 1;
    this.geos.push(ng);
    this.group.add(this.tiles, this.names);
  }

  /** Where tile (col, row)'s top-left corner rests (group space: tile px, y up from the field's top edge). */
  static corner(col: number, row: number, target = new THREE.Vector3()) {
    return target.set(col * PITCH.x, -row * PITCH.y, 0);
  }

  /** The field's extent after n doublings (group space): its centre, width and height. */
  static extent(cols: number, rows: number) {
    const w = cols * PITCH.x - TILE.gap, h = rows * PITCH.y - TILE.gap;
    return { cx: w / 2, cy: -h / 2, w, h };
  }

  set(look: FieldLook) {
    this.u.uTime!.value = look.t;
    const land = this.u.uLand!.value as number[];
    for (let k = 0; k < DOUBLINGS; k++) land[k] = look.land[k] ?? 1e9;
    this.u.uFade!.value = look.fade;
    this.u.uDetail!.value = look.detail;
    (this.u.uSweep!.value as THREE.Vector4).set(look.sweep[0], look.sweep[1], look.sweep[2], 0);
    this.group.visible = look.fade > 0.002;
  }

  dispose() {
    for (const g of this.geos) g.dispose();
    this.tileMat.dispose();
    this.nameMat.dispose();
    this.atlas.dispose();
  }
}
