// The Merkle tree of scene `merkle` on the GPU: its 11,110 edges as hairlines and its 11,111 nodes as dots, each one
// instanced draw whose vertex shader animates it as a pure function of the scene's time and a few uniforms. The CPU
// sets those uniforms and nothing else per frame: every node's and edge's times (when the moss reaches it, when the
// walk does, when its subtree folds) are attributes built once in init.
//
// What the shaders do:
// - The fold. A skipped subtree closes like an umbrella about its root F: its cone narrows to the vertical under F,
//   then draws up into F, its lines fading as they go; the stub from F's parent stays and darkens, and F seals (a ring
//   round its dot).
// - The moss. A changed file pulses moss, and the moss climbs its path to the root, edge by edge: each edge lights from
//   its child end up, a hot front leading. Lit lines are thicker (a thin bright line steps through the bloom).
// - The walk. A comet runs down every lit path from the root, one level a word; where it passes, the subtrees beside
//   it fold (their times say so). The files it reaches flash.
// - Light. Bone lines and dots, dimmer the deeper the level, a band of light sweeping the tree (bone never blooms: it
//   stays under display white), and the far side falling off into the dark.
//
// Lines are capsules in screen space (engine/lines.ts's shape) with a width in px and a floor in metres, so a line the
// camera dives past thickens as a real thread would. Each draw comes twice: a depth pass first (the core of every line
// and dot writes its depth, so the depth of field focuses on the tree) and then the light, added with no depth test
// (crossing hairlines add up instead of cutting each other).
import * as THREE from 'three';
import { HEX } from '../engine/palette';
import { glow } from '../engine/look';
import { BRANCH, DEPTH, N, levelOf, parentOf, type Tree } from './merkle-tree';

/** A time that never comes (s). */
export const NEVER = 1e6;

const f = (x: number) => x.toFixed(5);
const srgb = (c: string) => {
  const n = parseInt(c.slice(1), 16);
  return `vec3(${[(n >> 16) & 255, (n >> 8) & 255, n & 255].map((x) => (x / 255).toFixed(5)).join(', ')})`;
};
const v3 = (c: readonly number[]) => `vec3(${c.map(f).join(', ')})`;

/** The uniforms both draws share (one object: set once a frame). */
export function treeUniforms() {
  return {
    /** Scene time (s since the scene's start). */
    uT: { value: 0 },
    /** Logical frame size (px), physical px per logical px. */
    uScreen: { value: new THREE.Vector3(1920, 1080, 1) },
    /** The fold: its length (s), the share of it the cone takes to close, where the draw-up starts (share). */
    uFold: { value: new THREE.Vector3(0.42, 0.55, 0.3) },
    /** Line widths: bone (px), lit (px), the floor in metres, the near plane (m, view depth). */
    uWidth: { value: new THREE.Vector4(1, 1.7, 0.00007, 0.004) },
    /** Bone level of edges into each level 1..4 (b of the way from ink to bone). */
    uEdgeB: { value: new THREE.Vector4(0.48, 0.38, 0.27, 0.17) },
    /** Bone level of dots by level 0..3 and the leaves' (vec4 + float). */
    uDotB: { value: new THREE.Vector4(0.85, 0.72, 0.6, 0.5) },
    uLeafB: { value: 0.45 },
    /** Dot radius (px) by level 0..3, and the leaves'. */
    uDotR: { value: new THREE.Vector4(4.5, 3.2, 2.2, 1.6) },
    uLeafR: { value: 1.25 },
    /** A dot's floor radius (m): near the lens a node is a bead, not a point. */
    uDotM: { value: 0.00028 },
    /** The moss: its glow level lit, and at the hot front; the walk's comet level. */
    uMoss: { value: new THREE.Vector3(1.5, 4, 5) },
    /** How much brighter the dive's own path burns once the walk has passed down it. */
    uDive: { value: 1.6 },
    /** The whole tree's light (0..1), a breath on the beat (added b), the far falloff: from, to (m), level there. */
    uLight: { value: new THREE.Vector4(1, 0, 0, 0) },
    uFar: { value: new THREE.Vector3(1.5, 3.5, 0.4) },
    /** A band of light: its plane's normal and offset (m), its half-width (m), its strength (added b). */
    uSweep: { value: new THREE.Vector4(1, 0, 0, 99) },
    uSweepK: { value: new THREE.Vector2(0.06, 0) },
    /** How dark a sealed subtree's stub and node go (0..1 of their light kept). */
    uSealed: { value: 0.32 },
  };
}
export type TreeUniforms = ReturnType<typeof treeUniforms>;

/** GLSL both vertex shaders share: the uniforms, the fold, bone as the eye sees it. */
const COMMON = /* glsl */ `
precision highp float;
uniform mat4 projectionMatrix, viewMatrix;
uniform float uT;
uniform vec3 uScreen;
uniform vec3 uFold;
uniform vec4 uWidth;
uniform vec4 uEdgeB, uDotB, uDotR;
uniform float uLeafB, uLeafR, uDotM;
uniform vec3 uMoss;
uniform float uDive;
uniform vec4 uLight;
uniform vec3 uFar;
uniform vec4 uSweep;
uniform vec2 uSweepK;
uniform float uSealed;
const vec3 INK_S = ${srgb(HEX.ink)};
const vec3 BONE_S = ${srgb(HEX.bone)};
const vec3 MOSS = ${v3(glow('moss', 1))};
float lin(float c) { return c < 0.04045 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4); }
// b of the way from ink to bone as the eye sees it, as light added over ink
vec3 boneAt(float b) {
  vec3 s = mix(INK_S, BONE_S, clamp(b, 0.0, 1.0));
  return vec3(lin(s.r), lin(s.g), lin(s.b)) - vec3(lin(INK_S.r), lin(INK_S.g), lin(INK_S.b));
}
// a fold's progress at uT: 0 before it starts, 1 when it is shut
float foldU(vec4 F) { return F.w > 1e5 ? 0.0 : clamp((uT - F.w) / uFold.x, 0.0, 1.0); }
// a point of a subtree folding about its root F: the cone closes to the vertical under F, then draws up into F
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
// light on the tree at a world point: the band sweeping it, the far side falling off
float lightAt(vec3 w, float viewZ) {
  float band = dot(w, uSweep.xyz) - uSweep.w;
  float s = uSweepK.y * exp(-band * band / (uSweepK.x * uSweepK.x));
  float far = mix(1.0, uFar.z, smoothstep(uFar.x, uFar.y, viewZ));
  return far * uLight.x + s;
}
`;

// ------------------------------------------------------------------------------------------------ edges

const EDGE_VERT = /* glsl */ `${COMMON}
in vec3 position; // the quad: x 0 at the parent end, 1 at the child end; y -1..1 across
in vec4 aP;  // the parent at rest; the child's level
in vec4 aC;  // the child at rest; flags: 1 lit, 2 on the dive, 4 a fold's stub (its child is the fold's root)
in vec4 aF;  // the fold it is in: its root, when it starts (s); NEVER: none
in vec4 aT;  // the moss reaches the child, the parent; the walk reaches the parent, the child (s)
out vec2 vLocal;  // px along the segment (from the parent end's centre) and across
out float vLen;   // px
out vec2 vHalfW;  // half widths: bone, lit (px)
out vec4 vCol;    // bone light, alpha
out vec2 vU;      // edge parameter here (0 parent, 1 child); unused
out vec4 vMoss;   // lit share from the child end (0..1), the front's heat, the comet's place (edge parameter), its level
out float vMossK; // the moss's own strength here: the far side's falloff, the dive's path burning brighter

vec4 clipOf(vec3 v) { return projectionMatrix * vec4(v, 1.0); }

void main() {
  float level = aP.w, flags = aC.w;
  bool lit = mod(flags, 2.0) > 0.5;
  bool stub = mod(floor(flags / 4.0), 2.0) > 0.5;
  float fu = foldU(aF);
  // the fold moves both ends of an edge inside a skipped subtree; a stub stays where it is
  vec3 pa = stub ? aP.xyz : folded(aP.xyz, aF);
  vec3 pb = stub ? aC.xyz : folded(aC.xyz, aF);
  vec3 va = (viewMatrix * vec4(pa, 1.0)).xyz, vb = (viewMatrix * vec4(pb, 1.0)).xyz;
  // clip at the near plane (a line the camera dives past)
  float zn = -uWidth.w;
  float ua = 0.0, ub = 1.0;
  if (va.z > zn && vb.z > zn) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); return; }
  if (va.z > zn) { float s = (zn - va.z) / (vb.z - va.z); va = mix(va, vb, s); ua = s; }
  if (vb.z > zn) { float s = (zn - vb.z) / (va.z - vb.z); vb = mix(vb, va, s); ub = 1.0 - s; }
  vec4 ca = clipOf(va), cb = clipOf(vb);
  vec2 res = uScreen.xy * uScreen.z;
  vec2 sa = ca.xy / ca.w * 0.5 * res, sb = cb.xy / cb.w * 0.5 * res;
  // width: px, or the floor in metres where that is wider (px per metre at each end)
  float k = projectionMatrix[1][1] * 0.5 * res.y;
  float wm = uWidth.z * k * mix(1.0 / ca.w, 1.0 / cb.w, position.x);
  float wBone = max(uWidth.x * uScreen.z, wm), wLit = max(uWidth.y * uScreen.z, 1.2 * wm);
  float hw = 0.5 * (lit ? max(wBone, wLit) : wBone) + 1.0;
  vec2 d = sb - sa;
  float len = length(d);
  vec2 dir = len > 1e-4 ? d / len : vec2(1.0, 0.0), nrm = vec2(-dir.y, dir.x);
  float along = mix(-hw, len + hw, position.x);
  vec2 p = sa + dir * along + nrm * position.y * hw;
  float z = mix(ca.z / ca.w, cb.z / cb.w, position.x);
  gl_Position = vec4(p / (0.5 * res), z, 1.0);
  vLocal = vec2(along, position.y * hw);
  vLen = len;
  vHalfW = 0.5 * vec2(wBone, wLit);
  vU = vec2(mix(ua, ub, clamp(along / max(len, 1e-3), 0.0, 1.0)), 0.0);

  // light: bone by level, darkening as its subtree folds (a stub to a sealed root keeps a little)
  vec3 mid = mix(pa, pb, 0.5);
  float midZ = -mix(va.z, vb.z, 0.5);
  float b = (level < 1.5 ? uEdgeB.x : level < 2.5 ? uEdgeB.y : level < 3.5 ? uEdgeB.z : uEdgeB.w) + uLight.y;
  b *= lightAt(mid, midZ);
  bool dive = mod(floor(flags / 2.0), 2.0) > 0.5;
  vMossK = mix(1.0, uFar.z, smoothstep(uFar.x, uFar.y, midZ)) * (dive ? mix(1.0, uDive, smoothstep(0.0, 0.2, uT - aT.w)) : 1.0);
  float alpha = 1.0;
  if (stub) b *= mix(1.0, uSealed, smoothstep(0.0, 0.7, fu));
  else if (aF.w < 1e5) {
    // as the cone closes its lines crowd together: each dims so the bundle never flares, then fades as it draws up
    float close = smoothstep(0.0, uFold.y, fu);
    b *= (1.0 - 0.92 * close) * (1.0 - 0.5 * smoothstep(0.0, 0.5, fu));
    alpha = 1.0 - smoothstep(0.35, 0.9, fu);
  }
  vCol = vec4(boneAt(b), alpha);
  // the moss climbs from the child end; the comet runs down from the parent end
  vMoss = vec4(0.0, 0.0, -9.0, 0.0);
  if (lit) {
    float m = clamp((uT - aT.x) / max(aT.y - aT.x, 1e-3), 0.0, 1.0);
    vMoss.x = uT < aT.x ? 0.0 : m;
    vMoss.y = uT < aT.x ? 0.0 : 1.0 - smoothstep(0.0, 0.18, uT - aT.y); // the front is hot until it has passed
    float c = (uT - aT.z) / max(aT.w - aT.z, 1e-3);
    if (c > -0.2 && c < 1.4) vMoss.zw = vec2(c, 1.0);
  }
  if (alpha <= 0.0 && !lit) gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
}`;

const EDGE_FRAG = /* glsl */ `
precision highp float;
uniform vec3 uMoss;
in vec2 vLocal;
in float vLen;
in vec2 vHalfW;
in vec4 vCol;
in vec2 vU;
in vec4 vMoss;
in float vMossK;
out vec4 fragColor;
const vec3 MOSS = ${v3(glow('moss', 1))};
void main() {
  float u = vU.x;
  // lit from the child end (u = 1) back to the front
  float litK = vMoss.x > 0.0 ? smoothstep(-0.04, 0.0, u - (1.0 - vMoss.x)) : 0.0;
  float front = vMoss.y * exp(-pow((u - (1.0 - vMoss.x)) / 0.08, 2.0)) * step(0.0, vMoss.x - 0.001) * step(vMoss.x, 0.999);
  float c = vMoss.z, comet = 0.0;
  if (vMoss.w > 0.0) {
    float dx = u - c;
    comet = dx > 0.0 ? exp(-pow(dx / 0.05, 2.0)) : exp(dx / 0.22);
    comet *= step(dx, 0.12) * clamp(1.0 - (c - 1.0) / 0.4, 0.0, 1.0);
  }
  float moss = max(litK, comet);
  float halfW = mix(vHalfW.x, vHalfW.y, moss);
  float x = clamp(vLocal.x, 0.0, vLen);
  float d = length(vec2(vLocal.x - x, vLocal.y)) - halfW;
  // thinner than 0.7 px: fade instead of shrinking
  float cov = clamp(0.5 - d, 0.0, 1.0) * min(1.0, 2.0 * halfW / 0.7);
#ifdef DEPTH_PASS
  if (cov * vCol.a < 0.5) discard;
  fragColor = vec4(0.0);
#else
  vec3 col = mix(vCol.rgb, MOSS * uMoss.x * vMossK, litK) + MOSS * (uMoss.y * front + uMoss.z * comet);
  float a = cov * max(vCol.a, moss);
  if (a <= 0.002) discard;
  fragColor = vec4(col * a, a);
#endif
}`;

// ------------------------------------------------------------------------------------------------ nodes

const NODE_VERT = /* glsl */ `${COMMON}
in vec2 corner; // the quad, -1..1
in vec4 aN;  // the node at rest; its level
in vec4 aF;  // the fold it is in: its root, when it starts (s)
in vec4 aT;  // the moss reaches it, the walk does (s); flags: 1 lit, 2 on the dive, 4 a fold's root, 8 a changed file; seed
out vec2 vXY;    // px from the centre
out float vR;    // radius (px)
out vec4 vCol;   // light, alpha
out vec2 vRing;  // the sealed ring's radius (px), its alpha
void main() {
  float level = aN.w, flags = aT.z;
  bool lit = mod(flags, 2.0) > 0.5;
  bool root = mod(floor(flags / 4.0), 2.0) > 0.5;
  bool file = mod(floor(flags / 8.0), 2.0) > 0.5;
  float fu = foldU(aF);
  vec3 p = root ? aN.xyz : folded(aN.xyz, aF);
  vec4 v = viewMatrix * vec4(p, 1.0);
  if (v.z > -uWidth.w) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); return; }
  vec4 c = projectionMatrix * v;
  vec2 res = uScreen.xy * uScreen.z;
  float kpx = projectionMatrix[1][1] * 0.5 * res.y / c.w;
  float r0 = level < 0.5 ? uDotR.x : level < 1.5 ? uDotR.y : level < 2.5 ? uDotR.z : level < 3.5 ? uDotR.w : uLeafR;
  float r = max(r0 * uScreen.z, uDotM * kpx * (level > 3.5 ? 0.6 : 1.0));
  float b = level < 0.5 ? uDotB.x : level < 1.5 ? uDotB.y : level < 2.5 ? uDotB.z : level < 3.5 ? uDotB.w : uLeafB;
  b = (b + uLight.y) * lightAt(p, -v.z);
  float alpha = 1.0;
  vec3 col;
  // sealed: a fold's root dims and takes a ring; what folds into it fades as it arrives
  float seal = root ? smoothstep(0.35, 0.8, fu) : 0.0;
  if (root) b *= mix(1.0, uSealed * 1.4, seal);
  else if (aF.w < 1e5) {
    // a folding subtree's dots crowd into its root: each dims so they never pile up into a flare, and goes
    b *= 1.0 - 0.85 * smoothstep(0.0, uFold.y, fu);
    alpha = 1.0 - smoothstep(0.2, 0.6, fu);
  }
  col = boneAt(b);
  if (lit) {
    // the moss reaches it (a changed file pulses: a flash settling to the lit level), the walk flashes it
    float m = smoothstep(0.0, 0.05, uT - aT.x);
    float flash = uT < aT.x ? 0.0 : exp(-(uT - aT.x) / (file ? 0.16 : 0.1));
    float walk = uT < aT.y ? 0.0 : exp(-(uT - aT.y) / 0.14);
    float far = mix(1.0, uFar.z, smoothstep(uFar.x, uFar.y, -v.z));
    col = mix(col, MOSS * uMoss.x * 1.15 * far, m) + MOSS * (uMoss.y * (file ? 1.2 : 0.6) * flash + uMoss.z * 0.8 * walk);
    r *= 1.0 + m * (file ? 0.6 : 0.35) + 0.9 * flash + 0.8 * walk;
  }
  float ring = root ? 2.6 * r + 1.5 * uScreen.z : 0.0;
  float ext = (root ? ring : r) + 1.5 * uScreen.z;
  vec2 s = c.xy / c.w * 0.5 * res + corner * ext;
  gl_Position = vec4(s / (0.5 * res), c.z / c.w, 1.0);
  vXY = corner * ext;
  vR = r;
  vCol = vec4(col, alpha);
  vRing = vec2(ring, seal * alpha);
}`;

const NODE_FRAG = /* glsl */ `
precision highp float;
uniform vec3 uScreen;
in vec2 vXY;
in float vR;
in vec4 vCol;
in vec2 vRing;
out vec4 fragColor;
const vec3 RING = ${v3([0, 1, 2].map((i) => Math.pow((parseInt(HEX.boneFaint.slice(1 + 2 * i, 3 + 2 * i), 16) / 255 + 0.055) / 1.055, 2.4)))};
void main() {
  float d = length(vXY);
  float dot_ = clamp(vR + 0.5 - d, 0.0, 1.0) * vCol.a;
  float ring = vRing.y * clamp(0.75 * uScreen.z + 0.5 - abs(d - vRing.x), 0.0, 1.0);
#ifdef DEPTH_PASS
  if (max(dot_, ring) < 0.5) discard;
  fragColor = vec4(0.0);
#else
  float a = max(dot_, ring);
  if (a <= 0.002) discard;
  vec3 col = (vCol.rgb * dot_ + RING * 0.6 * ring * (1.0 - dot_));
  fragColor = vec4(col, a);
#endif
}`;

// ------------------------------------------------------------------------------------------------ the draws

/** Per-node times the shaders read (scene time, s): the moss's arrival, the walk's, the fold each node is in. */
export interface TreeTimes {
  /** When the moss reaches a node (lit nodes; NEVER otherwise). */
  moss: Float32Array;
  /** When the walk reaches a node (lit nodes). */
  walk: Float32Array;
  /** When each fold root's subtree starts to fold (by root id; NEVER where a node roots none). */
  fold: Float32Array;
}

function material(vert: string, frag: string, u: TreeUniforms, depth: boolean) {
  const m = new THREE.RawShaderMaterial({
    glslVersion: THREE.GLSL3,
    vertexShader: vert,
    fragmentShader: (depth ? '#define DEPTH_PASS\n' : '') + frag,
    uniforms: u,
    transparent: !depth,
    depthTest: depth,
    depthWrite: depth,
    colorWrite: !depth,
    blending: depth ? THREE.NoBlending : THREE.CustomBlending,
  });
  if (!depth) {
    m.blendEquation = THREE.AddEquation;
    m.blendSrc = m.blendSrcAlpha = THREE.OneFactor;
    m.blendDst = THREE.OneFactor; // light adds
    m.blendDstAlpha = THREE.OneMinusSrcAlphaFactor;
  }
  return m;
}

/** The whole tree: a group of four meshes (the edges' and the dots' depth, then their light). */
export class TreeDraw {
  group = new THREE.Group();
  u = treeUniforms();
  private geos: THREE.InstancedBufferGeometry[] = [];
  private mats: THREE.RawShaderMaterial[] = [];

  constructor(tree: Tree, times: TreeTimes, onDive: ReadonlySet<number>) {
    const { pos, lit, fold } = tree;
    const P = (id: number) => [pos[id * 3]!, pos[id * 3 + 1]!, pos[id * 3 + 2]!];
    const foldOf = (id: number) => {
      const r = fold[id]!;
      return r < 0 ? [0, 0, 0, NEVER] : [...P(r), times.fold[r]!];
    };

    // edges: one per child node
    const E = N - 1;
    const eP = new Float32Array(E * 4), eC = new Float32Array(E * 4), eF = new Float32Array(E * 4), eT = new Float32Array(E * 4);
    for (let c = 1; c < N; c++) {
      const p = parentOf(c), i = c - 1;
      eP.set([...P(p), levelOf(c)], i * 4);
      const flags = (lit[c] ? 1 : 0) + (onDive.has(c) ? 2 : 0) + (fold[c] === c ? 4 : 0);
      eC.set([...P(c), flags], i * 4);
      eF.set(foldOf(c), i * 4);
      eT.set([times.moss[c]!, times.moss[p]!, times.walk[p]!, times.walk[c]!], i * 4);
    }
    const eg = new THREE.InstancedBufferGeometry();
    eg.setAttribute('position', new THREE.BufferAttribute(new Float32Array([0, -1, 0, 1, -1, 0, 1, 1, 0, 0, 1, 0]), 3));
    eg.setIndex([0, 1, 2, 0, 2, 3]);
    for (const [name, arr] of [['aP', eP], ['aC', eC], ['aF', eF], ['aT', eT]] as const) eg.setAttribute(name, new THREE.InstancedBufferAttribute(arr, 4));
    eg.instanceCount = E;

    // nodes
    const nN = new Float32Array(N * 4), nF = new Float32Array(N * 4), nT = new Float32Array(N * 4);
    for (let id = 0; id < N; id++) {
      const k = levelOf(id);
      nN.set([...P(id), k], id * 4);
      nF.set(foldOf(id), id * 4);
      const flags = (lit[id] ? 1 : 0) + (onDive.has(id) ? 2 : 0) + (fold[id] === id ? 4 : 0) + (lit[id] && k === DEPTH ? 8 : 0);
      nT.set([times.moss[id]!, times.walk[id]!, flags, (id * 0.618034) % 1], id * 4);
    }
    const ng = new THREE.InstancedBufferGeometry();
    ng.setAttribute('corner', new THREE.BufferAttribute(new Float32Array([-1, -1, 1, -1, 1, 1, -1, 1]), 2));
    ng.setIndex([0, 1, 2, 0, 2, 3]);
    for (const [name, arr] of [['aN', nN], ['aF', nF], ['aT', nT]] as const) ng.setAttribute(name, new THREE.InstancedBufferAttribute(arr, 4));
    ng.instanceCount = N;
    this.geos.push(eg, ng);

    // the depth of every line's and dot's core first, then their light
    const add = (g: THREE.InstancedBufferGeometry, vert: string, frag: string, depth: boolean, order: number) => {
      const m = material(vert, frag, this.u, depth);
      this.mats.push(m);
      const mesh = new THREE.Mesh(g, m);
      mesh.frustumCulled = false;
      mesh.renderOrder = order;
      this.group.add(mesh);
    };
    add(eg, EDGE_VERT, EDGE_FRAG, true, -20);
    add(ng, NODE_VERT, NODE_FRAG, true, -19);
    add(eg, EDGE_VERT, EDGE_FRAG, false, -10);
    add(ng, NODE_VERT, NODE_FRAG, false, -9);
  }

  dispose() {
    for (const g of this.geos) g.dispose();
    for (const m of this.mats) m.dispose();
  }
}

/** Branching, for the scene's own arithmetic. */
export { BRANCH };
