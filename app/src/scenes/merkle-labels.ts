// The tree's labels on the GPU (engine/glyphs.ts): every internal node's hash, seven mono hex digits beside its dot, and
// a stamp, `= hash · skipped`, under each skipped subtree's root as it seals. One instanced draw of glyph cells, posed
// by a vertex shader as a pure function of the scene's time, like the tree itself (merkle-gl.ts); the engine's
// fragment shader draws them (and their split-flap).
//
// - Labels face the camera and keep their size in the world, so the camera's dive brings them up to legible as it
//   passes; one too small to read (under a few px an em) is not drawn at all, so the wide shots carry only the
//   top-level hashes and the rest of the tree reads as its hairlines.
// - A changed node's hash is recomputed as the moss reaches it: its digits split-flap to the new hash, left to right,
//   and it turns moss (changed, `+`).
// - A skipped subtree's labels fold into its root with it and go; the root keeps its hash (dimmed with it) and the stamp
//   hits under it: down from a size and a half as the umbrella shuts.
import * as THREE from 'three';
import { GLYPH_VERT_HEAD, glyphMaterial, glyphQuad, type GlyphAtlas } from '../engine/glyphs';
import { glow } from '../engine/look';
import { DEPTH, N, hashOf, levelOf, type Tree } from './merkle-tree';
import type { TreeUniforms } from './merkle-gl';
import { NEVER, STAMP_AT, type TreeTimes } from './merkle-time';

/** The characters the labels use: the hex digits first (digit d at atlas index d), then the stamp's. */
export const LABEL_CHARS = '0123456789abcdef=·hskiped';
/** A label's em (m) by level, root first, the files last: about a fifth of the gap to the node's nearest sibling. */
const EM = [0.017, 0.0115, 0.0052, 0.0019, 0.0011] as const;
const f = (x: number) => x.toFixed(5);
const v3 = (c: readonly number[]) => `vec3(${c.map(f).join(', ')})`;

const LABEL_VERT = /* glsl */ `${GLYPH_VERT_HEAD}
in vec4 aA; // the node at rest; the label's em (m)
in vec4 aF; // the fold it is in: its root, when it starts (s)
in vec4 aG; // column, row (0 the hash, 1 the stamp), glyph, the glyph it flips to
in vec4 aT; // when its hash flips (s), when its stamp hits (s), flags (1 lit, 2 a fold's root, 4 inside a fold), seed
uniform float uT;
uniform vec3 uScreen;
uniform vec3 uFold;
uniform vec4 uLabel; // bone level of a hash, of a stamp; the px an em must reach to show, and to show whole
uniform vec4 uDefocus; // 1 / the focus distance (1/m), K (logical px of blur per 1/m), and the blur (px) labels fade over
uniform vec4 uLight;
uniform float uSealed;
const vec3 MOSS = ${v3(glow('moss', 1))};
float h1(float x) { return fract(sin(x * 127.1 + 311.7) * 43758.5453); }
float foldU(vec4 F) { return F.w > 1e5 ? 0.0 : clamp((uT - F.w) / uFold.x, 0.0, 1.0); }
vec3 folded(vec3 p, vec4 F) {
  float u = foldU(F);
  if (u <= 0.0) return p;
  float close = smoothstep(0.0, uFold.y, u);
  float up = smoothstep(uFold.z, 1.0, u);
  up = up * up * (3.0 - 2.0 * up);
  vec3 d = p - F.xyz;
  d.xz *= 1.0 - close;
  return F.xyz + d * (1.0 - up);
}
void main() {
  float flags = aT.z, seed = aT.w;
  bool lit = mod(flags, 2.0) > 0.5;
  bool root = mod(floor(flags / 2.0), 2.0) > 0.5;
  bool inside = mod(floor(flags / 4.0), 2.0) > 0.5;
  float col = aG.x, row = aG.y, em = aA.w;
  float fu = foldU(aF);
  vec3 p = inside ? folded(aA.xyz, aF) : aA.xyz;
  vec3 R = vec3(viewMatrix[0][0], viewMatrix[1][0], viewMatrix[2][0]);
  vec3 U = vec3(viewMatrix[0][1], viewMatrix[1][1], viewMatrix[2][1]);
  vec4 cp = projectionMatrix * viewMatrix * vec4(p, 1.0);
  float emPx = em * projectionMatrix[1][1] * 0.5 * uScreen.y / max(cp.w, 1e-4);
  float alpha = smoothstep(uLabel.z, uLabel.w, emPx) * step(0.0, cp.w);
  // what the lens has thrown out of focus goes: a label is read where the eye is sent, not smeared everywhere else
  float coc = uDefocus.y * abs(uDefocus.x - 1.0 / max(cp.w, 1e-4));
  alpha *= 1.0 - smoothstep(uDefocus.z, uDefocus.w, coc);
  float b = uLabel.x;
  vec3 colr;
  vec4 glyph = vec4(aG.z, -1.0, 0.0, 0.0);
  // the stamp: it hits as the subtree seals, from a size and a half, and stays
  float s = 1.0;
  if (row > 0.5) {
    float dt = uT - aT.y;
    alpha *= smoothstep(0.0, 0.035, dt);
    s = 1.0 + 0.5 * exp(-max(dt, 0.0) / 0.045);
    b = uLabel.y * (1.0 + 0.8 * exp(-max(dt, 0.0) / 0.08));
  }
  // a sealed root's hash dims with it (its stamp stays bright: it is the news)
  if (root && row < 0.5) b *= mix(1.0, uSealed * 1.6, smoothstep(0.35, 0.8, fu));
  if (inside) alpha *= 1.0 - smoothstep(0.15, 0.5, fu);
  colr = boneAt(b * uLight.x);
  // a changed node's hash flips as the moss reaches it: two to four flaps a digit, landing left to right
  if (lit && row < 0.5) {
    float flap = 0.045, land = aT.x + 0.1 + 0.022 * col;
    float steps = 2.0 + floor(h1(seed * 7.1 + col * 1.3) * 3.0), t0 = land - steps * flap;
    if (uT >= land) glyph.x = aG.w;
    else if (uT >= t0) {
      float u = (uT - t0) / flap, k = min(steps - 1.0, floor(u)), pr = u - k;
      float from = k < 0.5 ? aG.z : floor(h1(seed * 3.3 + col * 2.1 + k * 5.7) * 16.0);
      float to = k > steps - 1.5 ? aG.w : floor(h1(seed * 3.3 + col * 2.1 + (k + 1.0) * 5.7) * 16.0);
      glyph = vec4(from, to, pr * pr, 1.0);
    }
    float m = smoothstep(aT.x, aT.x + 0.25, uT);
    colr = mix(colr, MOSS * 0.85, m) + MOSS * 1.2 * exp(-max(uT - land, 0.0) / 0.12) * step(t0, uT);
  }
  // the cell: right of the dot and centred on it (the hash), the stamp a line under it
  vec2 o = vec2(0.75 + col * 0.6, row < 0.5 ? -0.36 : -1.75);
  vec2 e = vec2(CELL_X0 + corner.x * CELL_W, CELL_Y0 + corner.y * CELL_H);
  vec2 q = row > 0.5 ? vec2(0.75, -1.75) + (o + e - vec2(0.75, -1.75)) * s : o + e;
  vec3 world = p + (R * q.x + U * q.y) * em;
  vUv = corner;
  vGlyph = glyph;
  vCol = vec4(colr, alpha);
  vTile = vec2(0.0, 1.0);
  if (alpha <= 0.002 || glyph.x < -0.5) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); return; }
  gl_Position = projectionMatrix * viewMatrix * vec4(world, 1.0);
}`;

/** The stamp under a skipped subtree's root. */
export const STAMP = '= hash · skipped';

export class LabelField {
  mesh: THREE.Mesh;
  private geo: THREE.InstancedBufferGeometry;
  private mat: THREE.RawShaderMaterial;
  readonly u: { uLabel: THREE.IUniform<THREE.Vector4>; uDefocus: THREE.IUniform<THREE.Vector4> };

  /**
   * Every internal node's hash, and the stamp under each skipped subtree's root above the files (`stamp` its text,
   * from the strings file). `tu` are the tree's uniforms (shared: one clock, one fold).
   */
  constructor(tree: Tree, times: TreeTimes, atlas: GlyphAtlas, tu: TreeUniforms, stamp: string) {
    const A: number[] = [], F: number[] = [], G: number[] = [], Tt: number[] = [];
    const { pos, lit, fold } = tree;
    const at = (id: number) => [pos[id * 3]!, pos[id * 3 + 1]!, pos[id * 3 + 2]!];
    const push = (id: number, col: number, row: number, g: number, g2: number, flip: number, hit: number) => {
      const k = levelOf(id), r = fold[id]!;
      A.push(...at(id), EM[k]!);
      F.push(...(r < 0 ? [0, 0, 0, NEVER] : [...at(r), times.fold[r]!]));
      G.push(col, row, g, g2);
      const flags = (lit[id] ? 1 : 0) + (r === id ? 2 : 0) + (r >= 0 && r !== id ? 4 : 0);
      Tt.push(flip, hit, flags, ((id * 0.618034) % 1) * 0.999);
    };
    for (let id = 0; id < N; id++) {
      const k = levelOf(id);
      // (a file carries its blob's hash only where it changed: the fifty the walk reads)
      if (k === DEPTH && !lit[id]) continue;
      const old = hashOf(id, 0), now = lit[id] ? hashOf(id, 1) : old;
      for (let c = 0; c < 7; c++) push(id, c, 0, atlas.of(old[c]!), atlas.of(now[c]!), lit[id] ? times.moss[id]! : NEVER, NEVER);
      if (fold[id] === id) {
        const hit = times.fold[id]! + STAMP_AT * tu.uFold.value.x;
        // (a directory of ten files is skipped by its "=" alone: a hundred whole stamps down there would be a texture)
        Array.from(k === DEPTH - 1 ? stamp.slice(0, 1) : stamp).forEach((ch, c) => {
          const g = atlas.of(ch);
          if (g >= 0) push(id, c, 1, g, g, NEVER, hit);
        });
      }
    }
    const n = A.length / 4;
    this.geo = new THREE.InstancedBufferGeometry();
    glyphQuad(this.geo);
    for (const [name, arr] of [['aA', A], ['aF', F], ['aG', G], ['aT', Tt]] as const) {
      this.geo.setAttribute(name, new THREE.InstancedBufferAttribute(new Float32Array(arr), 4));
    }
    this.geo.instanceCount = n;
    this.u = { uLabel: { value: new THREE.Vector4(0.62, 0.66, 4.5, 7.5) }, uDefocus: { value: new THREE.Vector4(0, 0, 3, 9) } };
    this.mat = glyphMaterial(LABEL_VERT, atlas, {
      uT: tu.uT, uScreen: tu.uScreen, uFold: tu.uFold, uLight: tu.uLight, uSealed: tu.uSealed, uLabel: this.u.uLabel,
      uDefocus: this.u.uDefocus,
    });
    this.mesh = new THREE.Mesh(this.geo, this.mat);
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = 2;
  }

  dispose() {
    this.geo.dispose();
    this.mat.dispose();
  }
}
