// The thread in 3D: the film's motif (spec §3). One luminous thread: a bone core with a blood-red `−` ply and a
// moss-green `+` ply laid round it (the identity is a git diff). It draws on, frays and snaps, strings beads, weaves.
//
// Construction. Plies of one colour twist together as equals: the classic 3-ply, the opening's bone thread (Blender
// B01). A bone first ply with coloured plies after it is the diff thread (spec §3; Plan 2 Tasks 10 and 25: "blood and
// moss plies twisting around the bone core"): the bone ply is that same 3-ply rope, and the coloured plies are laid in
// its grooves, the way rope is wormed. So the thread that snaps in the opening is the core of the one that re-forms.
// Each coloured strand touches the two bone plies either side, flush with the rope's surface, and the `−` lies one
// groove ahead of the `+`: along the thread every turn reads `−`, `+`, then bone, diff hunks between context. `core`
// overrides the choice. Inside, a thread is up to five tubes (three bone plies and two worms); the public ply indices
// stay the colours' (0 the bone core, whose centre is the axis; 1 and 2 the strands).
//
// Geometry. The centreline is a centripetal Catmull-Rom through the points, resampled evenly in arc length into a
// float texture (`frames`, M samples × 4 rows: point, tangent, normal, binormal). The normal is a rotation-minimising
// frame (double reflection) started from world up, so it never flips at an inflection the way a Frenet frame does, and
// it is a pure function of the points. Each tube is its own round tube in one index buffer; its vertices carry only
// (arc fraction u, angle θ round the tube, tube index), and the vertex shader builds everything else from the texture:
// the ply centre on its helix round the axis, the tube round the ply, the tapered ends of the draw window, the fray.
// So setPoints uploads M × 4 texels and setDraw / setFray / setGlow set uniforms; nothing is rebuilt. The CPU mirror
// (pointAt, frameAt, plyCentre) reads the same float32 texels with the same formulas.
//
// Twist lives in material coordinates: ply phase = 2π · twist · (length at construction) · u. setPoints stretches the
// plies with the thread instead of sliding them along it, and the same points always give the same phase.
//
// Look (THREAD_LOOK holds every number; they are the reference the Blender thread matches, see its comment):
// - three's MeshPhysicalMaterial, so the scene's lights and the stage's studio light it, with its Charlie sheen (the
//   soft fibre sheen and rim) and anisotropic GGX: the highlight stretches across the fibres, so each ply turn carries
//   a streak where the half vector is square to the fibres, as on real cord.
// - The shader adds the fibre striation (grooves and per-fibre tone along iso-lines of vQ, which run with the
//   fibres), occlusion in the crevices where plies press together, and per-ply colour.
// - Blood and moss plies are dyed fibre (toward bloodDim and mossDim) with an emissive core in the palette colour:
//   glow('blood'|'moss', level) across the strand as a sharp power of N·V over a soft one, a luminous filament down its
//   middle that the post halates. Bone never emits.
// - Fibres off the surface are their own instanced mesh (a child of `mesh`): a sparse fuzz that catches the rim light
//   (Kajiya-Kay plus forward scatter), and fray fibres that grow and lift where setFray opens the plies.
import * as THREE from 'three';
import { GLSL_COMMON } from './glsl/common';
import { glow as glowLevel, type GlowKey } from './look';
import { LIN } from './palette';
import { mulberry32 } from './util';

export type ThreadColor = 'bone' | 'blood' | 'moss';

export interface ThreadOpts {
  /** Outer radius of the whole thread, world units. */
  radius: number;
  /** Plies (default 3). One ply is a single strand whose fibres carry the twist. */
  plies?: 1 | 2 | 3;
  /**
   * Ply turns per world unit of length, set against the length at construction (default: the lay angle
   * THREAD_LOOK.helixDeg at this radius). With one ply, the turns of its surface fibres.
   */
  twist?: number;
  /** Colour of each ply (default bone, blood, moss; cycled when shorter than `plies`). */
  colors?: ThreadColor[];
  /** Emissive level of the blood and moss cores: a look.ts glow() level, the bloom key at the core (default THREAD_LOOK.glow). */
  glow?: number;
  /** Segments round each tube (default 16). */
  radialSegments?: number;
  /** Rings along the thread (default: 24 per ply turn, at least 2 per radius of length; at most 4095). */
  tubularSegments?: number;
  /** The first ply is a 3-ply core with the others laid in its grooves (default: a bone first ply among other
   * colours, the diff thread). */
  core?: boolean;
  /** Fibres off the surface: 1 the look's density, 0 none (default 1). */
  fuzz?: number;
  /** Seed for where the fibres grow (default fixed). */
  seed?: number;
}

/**
 * The thread's look, one set of numbers for both renderers: the engine (here) and Blender (Task 8's thread.ply_thread
 * and materials.fiber). Lengths are in thread radii unless noted. The ply twist is right-handed (Z).
 */
export const THREAD_LOOK = {
  /** Equal plies (one colour), by count 1, 2, 3: ply radius and ply-centre offset. Three of radius 0.5 on a circle of
   * 0.5 overlap by 13%: plies pressed together, as a real twist compresses them. The outer radius stays 1. */
  plyRadius: [1, 0.5, 0.5],
  plyOffset: [0, 0.5, 0.5],
  /** Their lay angle against the thread axis (degrees); sets the default twist. */
  helixDeg: 32,
  /** The diff thread's coloured strands, laid in the grooves of the bone 3-ply: this radius, touching the plies either
   * side, puts them 0.8 from the axis, flush with the rope's outer radius. The grooves sit 1/6, 1/2 and 5/6 of a turn
   * round from the first ply; the `−` takes the one at 1/2 and the `+` the one at 1/6, so along the thread the `−`
   * passes each point a third of a turn before the `+`, and the groove at 5/6 is bare: `−`, `+`, then bone. */
  wormRadius: 0.2,
  /** A single strand's fibre angle (degrees against its axis). */
  singleDeg: 24,
  /** Surface fibres of a ply: 0 runs them along the ply, 1 along the thread axis on its crown (balanced). */
  fibreLay: 0.6,
  /** Fibres round a ply of radius 0.5 (in proportion to the radius): the striation; and how far a groove tilts the
   * normal. */
  fibres: 40,
  groove: 0.22,
  /** Where plies meet: the occlusion floor, and its reach round the ply (degrees) past the contact. */
  creviceAO: 0.35,
  creviceDeg: 55,
  /** The fibre surface. Roughness along the fibres; anisotropy raises it across them (the streak). */
  roughness: 0.42,
  anisotropy: 0.75,
  specular: 0.8,
  ior: 1.5,
  sheen: 1,
  sheenRoughness: 0.35,
  /** Blood and moss plies are dyed fibre: their albedo lies this far from the palette colour toward its dim shade
   * (bloodDim, mossDim), so the glowing core, in the palette colour itself, reads as light inside the strand. */
  dye: 0.82,
  /** The emissive core of blood and moss plies: its level (look.ts glow(), the brightest point), and its profile
   * across the strand, a filament inside translucent fibre: a sharp line, (N·V)^glowFalloff[0], over a soft scattered
   * base, (N·V)^glowFalloff[1], the base weighted glowSoft. Close up the line reads inside the strand; far off, the
   * strand glows. */
  glow: 3.4,
  glowFalloff: [28, 3],
  glowSoft: 0.2,
  /** Taper at the ends of the draw window. */
  tip: 5,
  /** Fray: half-width; at full fray the plies stand this much further out, swell, and untwist (their twist rate
   * at the centre drops to 1 − 2/3·untwist of normal, the twist moving to the shoulders so the rest never turns). */
  fraySpan: 10,
  fraySeparation: 1.4,
  fraySwell: 0.12,
  frayUntwist: 1.35,
  /** Fibres off the surface, per radius of length per tube: fuzz always, fray fibres where the fray opens. Lengths
   * and diameter in thread radii. */
  fuzzDensity: 2,
  frayDensity: 4,
  fuzzLength: [0.15, 0.5],
  frayLength: [0.4, 1.6],
  fibreWidth: 0.008,
} as const;

const TAU = Math.PI * 2;
const DEFAULT_COLORS: ThreadColor[] = ['bone', 'blood', 'moss'];
const GLOW_KEY: Record<ThreadColor, GlowKey | null> = { bone: null, blood: 'blood', moss: 'moss' };
const MAX_RINGS = 4095;
const MAX_TUBES = 5;
const MAX_FIBRES = 24000;
const FIBRE_SEGS = 6;
const deg = (d: number) => (d * Math.PI) / 180;

const clamp = (x: number, a: number, b: number) => (x < a ? a : x > b ? b : x);
const bump = (y: number) => (Math.abs(y) < 1 ? 0.5 + 0.5 * Math.cos(Math.PI * y) : 0);
const bumpInt = (y: number) => (y <= -1 ? 0 : y >= 1 ? 1 : 0.5 * (y + 1) + Math.sin(Math.PI * y) / TAU);
const glsl = (x: number) => (Number.isInteger(x) ? x.toFixed(1) : String(x));
/** Angle between two directions round a circle, 0..π. */
const angDist = (a: number, b: number) => Math.abs(Math.atan2(Math.sin(a - b), Math.cos(a - b)));

/**
 * One tube of the cross-section: radius and centre offset (thread radii), phase round the axis (turns), and the ply
 * (colour) it belongs to.
 */
interface Tube { r: number; d: number; phase: number; ply: number }

/**
 * The cross-section: equal plies on a circle, or the bone 3-ply with the other plies laid in its grooves. Also the lay
 * the default twist is set from: the angle, at the plies' offset.
 */
function layout(n: number, core: boolean): { tubes: Tube[]; layDeg: number; layOffset: number } {
  const L = THREAD_LOOK;
  if (n === 1) return { tubes: [{ r: 1, d: 0, phase: 0, ply: 0 }], layDeg: L.singleDeg, layOffset: 1 };
  if (core) {
    const r = L.plyRadius[2], d = L.plyOffset[2], rw = L.wormRadius;
    const bone = [0, 1, 2].map((i) => ({ r, d, phase: i / 3, ply: 0 }));
    // a groove lies between two plies (1/6 of a turn from each); a strand in it touching both sits D from the axis
    const D = d * Math.cos(Math.PI / 3) + Math.sqrt((r + rw) ** 2 - (d * Math.sin(Math.PI / 3)) ** 2);
    const worms = Array.from({ length: n - 1 }, (_, j) => ({ r: rw, d: D, phase: 0.5 - j / 3, ply: j + 1 }));
    return { tubes: [...bone, ...worms], layDeg: L.helixDeg, layOffset: d };
  }
  const r = L.plyRadius[n - 1]!, d = L.plyOffset[n - 1]!;
  return { tubes: Array.from({ length: n }, (_, i) => ({ r, d, phase: i / n, ply: i })), layDeg: L.helixDeg, layOffset: d };
}

/**
 * Where each tube meets the others, round the tube (θ = 0 its crown, away from the axis): up to two contacts, each the
 * direction of the neighbour and the half-width of the arc the neighbour's tube hides (the ones that hide most). Crevice
 * occlusion darkens toward them and fibres don't grow in them.
 */
function contacts(tubes: Tube[]): [number, number, number, number][] {
  return tubes.map((p, i) => {
    const ai = TAU * p.phase, cx = p.d * Math.cos(ai), cy = p.d * Math.sin(ai);
    const found: [number, number][] = [];
    tubes.forEach((q, j) => {
      if (j === i) return;
      const aj = TAU * q.phase, dx = q.d * Math.cos(aj) - cx, dy = q.d * Math.sin(aj) - cy;
      const D = Math.hypot(dx, dy);
      if (D > p.r + q.r + 0.02 || D < 1e-9) return;
      const hide = Math.acos(clamp((p.r * p.r + D * D - q.r * q.r) / (2 * p.r * D), -1, 1));
      found.push([Math.atan2(dy, dx) - ai, D < p.r + q.r ? hide : 0]);
    });
    found.sort((a, b) => b[1] - a[1]);
    const [c1, c2] = [found[0] ?? [0, -10], found[1] ?? found[0] ?? [0, -10]];
    return [c1[0], c2[0], c1[1], c2[1]];
  });
}

type Uniform<T> = { value: T };
export interface ThreadUniforms {
  tFrames: Uniform<THREE.DataTexture>;
  uM: Uniform<number>;
  uR: Uniform<number>;
  /** Ply turns over the whole thread (twist × the length at construction). */
  uTurns: Uniform<number>;
  /** Current length. */
  uLen: Uniform<number>;
  uTip: Uniform<number>;
  /** Visible window in arc fraction [p0, p1]. */
  uDraw: Uniform<THREE.Vector2>;
  /** Fray: at (arc fraction), amount (0..1), half-width (arc fraction of the length at construction). */
  uFray: Uniform<THREE.Vector3>;
  /** Per tube: radius and offset (thread radii), phase (turns), fibre drift (radians of θ per unit u). */
  uTube: Uniform<THREE.Vector4[]>;
  /** Per tube: two contact directions round the tube and the half-widths they hide (radians; < 0: none). */
  uContact: Uniform<THREE.Vector4[]>;
  /** Per tube: the ply it belongs to (the index into uColors and uGlow). */
  uTubePly: Uniform<number[]>;
  /** Per ply: the fibre's albedo (linear). */
  uColors: Uniform<THREE.Vector3[]>;
  /** Per ply: the emissive core (linear, the look.ts glow level); zero for bone. */
  uGlow: Uniform<THREE.Vector3[]>;
  /** Scales the along-fibre tone noise: arc fraction to fibre lengths. */
  uAlong: Uniform<number>;
  /** Physical px of the target being drawn (fibre widths are set in px). */
  uRes: Uniform<THREE.Vector2>;
}

// ------------------------------------------------------------------------------------------------ GLSL

/** The centreline and ply helix, shared by the ply and fibre vertex shaders (mirrored by Thread.plyCentre). */
const VERT_PARS = /* glsl */ `
uniform highp sampler2D tFrames;
uniform int uM;
uniform float uR, uTurns, uLen, uTip;
uniform vec2 uDraw;
uniform vec3 uFray;
uniform vec4 uTube[${MAX_TUBES}];
const float TH_TAU = 6.283185307179586;
const float TH_PI = 3.141592653589793;
const float TH_SEP = ${glsl(THREAD_LOOK.fraySeparation)};
const float TH_SWELL = ${glsl(THREAD_LOOK.fraySwell)};
const float TH_UNTWIST = ${glsl(THREAD_LOOK.frayUntwist)};
vec3 th_row(int i, int r) { return texelFetch(tFrames, ivec2(i, r), 0).xyz; }
void th_frame(float u, out vec3 C, out vec3 T, out vec3 N, out vec3 B) {
  float s = clamp(u, 0.0, 1.0) * float(uM - 1);
  int i0 = min(int(s), uM - 2);
  float f = s - float(i0);
  C = mix(th_row(i0, 0), th_row(i0 + 1, 0), f);
  T = normalize(mix(th_row(i0, 1), th_row(i0 + 1, 1), f));
  N = mix(th_row(i0, 2), th_row(i0 + 1, 2), f);
  N = normalize(N - dot(N, T) * T);
  B = cross(T, N);
}
float th_bump(float y) { return abs(y) < 1.0 ? 0.5 + 0.5 * cos(TH_PI * y) : 0.0; }
float th_bumpInt(float y) { return y <= -1.0 ? 0.0 : y >= 1.0 ? 1.0 : 0.5 * (y + 1.0) + sin(TH_PI * y) / TH_TAU; }
struct ThTube {
  vec3 P; vec3 T; vec3 N; vec3 B;   // tube centre and its frame: axis, outward (away from the thread axis), round
  float u; float rp; float d; float w; float tp; float drds; float rate; float secA; float K;
};
// Tube 'tube' at arc fraction u (clamped to the draw window): its centre and frame, radius, the fray and taper there.
ThTube th_tube(float u, float tube) {
  ThTube o;
  vec4 pl = uTube[int(tube + 0.5)];
  u = clamp(u, uDraw.x, uDraw.y);
  o.u = u;
  o.K = pl.w;
  float a = u - uDraw.x, b = uDraw.y - u;
  float x = clamp(min(a, b) * uLen / uTip, 0.0, 1.0);
  o.tp = 1.0 - (1.0 - x) * (1.0 - x);
  vec3 C, T, N, B;
  th_frame(u, C, T, N, B);
  float h = max(uFray.z, 1e-6), y = u - uFray.x;
  o.w = uFray.y * th_bump(y / h);
  float turns = uTurns * (u - TH_UNTWIST * uFray.y * h * (th_bumpInt(y / h) - th_bumpInt(y / (3.0 * h))));
  o.rate = uTurns * (1.0 - TH_UNTWIST * uFray.y * (th_bump(y / h) - th_bump(y / (3.0 * h)) / 3.0));
  float phi = TH_TAU * (turns + pl.z);
  vec3 radial = cos(phi) * N + sin(phi) * B, around = -sin(phi) * N + cos(phi) * B;
  o.d = uR * pl.y * (1.0 + TH_SEP * o.w) * mix(o.tp, 1.0, o.w);
  float rp0 = uR * pl.x * (1.0 + TH_SWELL * o.w);
  o.rp = rp0 * o.tp;
  o.drds = x < 1.0 ? rp0 * 2.0 * (1.0 - x) / uTip * (a < b ? 1.0 : -1.0) : 0.0;
  float phiP = TH_TAU * o.rate / uLen;
  o.secA = sqrt(1.0 + o.d * o.d * phiP * phiP);
  o.P = C + o.d * radial;
  o.T = normalize(T + o.d * phiP * around);
  o.N = normalize(radial - dot(radial, o.T) * o.T);
  o.B = cross(o.T, o.N);
  return o;
}
// Direction of the surface fibres at angle th round the tube: the iso-lines of vQ.
vec3 th_fibreDir(ThTube p, float th) {
  vec3 aTh = -sin(th) * p.N + cos(th) * p.B;
  return normalize(p.T * p.secA + p.rp * (TH_TAU * p.rate + p.K) / uLen * aTh);
}
// Fibres round a tube: in proportion to its radius, a whole number so the striation closes round it.
float th_fibres(float tube) { return floor(${glsl(THREAD_LOOK.fibres)} * uTube[int(tube + 0.5)].x / 0.5 + 0.5); }
`;

const PLY_VERT_PARS = /* glsl */ `
${VERT_PARS}
varying float vU;
varying float vTh;
varying float vTube;
varying float vQ;
varying float vW;
varying vec3 vFibre;
`;

const PLY_VERT_MAIN = /* glsl */ `
ThTube thp = th_tube(position.x, position.z);
float thTh = position.y;
vec3 thOff = cos(thTh) * thp.N + sin(thTh) * thp.B;
vec3 thPos = thp.P + thp.rp * thOff;
vec3 objectNormal = normalize(thOff - thp.drds * thp.T); // the taper leans the normal forward
vFibre = normalize((modelViewMatrix * vec4(th_fibreDir(thp, thTh), 0.0)).xyz);
vQ = th_fibres(position.z) / TH_TAU * (thTh - thp.K * thp.u);
vTh = thTh;
vTube = position.z;
vW = thp.w;
vU = thp.u;
#ifdef USE_TANGENT
  vec3 objectTangent = vec3(tangent.xyz);
#endif
`;

const PLY_FRAG_PARS = /* glsl */ `
#undef PI
${GLSL_COMMON}
uniform vec3 uColors[3];
uniform vec3 uGlow[3];
uniform vec4 uContact[${MAX_TUBES}];
uniform float uTubePly[${MAX_TUBES}];
uniform float uAlong;
varying float vU;
varying float vTh;
varying float vTube;
varying float vQ;
varying float vW;
varying vec3 vFibre;
float th_angDist(float a, float b) { float d = mod(a - b + PI, TAU) - PI; return abs(d); }
`;

/** Per-ply colour and the fibre striation (after color_fragment). */
const PLY_FRAG_COLOR = /* glsl */ `
int thTube = int(vTube + 0.5), thPi = int(uTubePly[thTube] + 0.5);
// the striation fades out before the fibres get closer than ~2 px, so it never aliases
float thDetail = 1.0 - smoothstep(0.3, 0.75, fwidth(vQ));
float thId = floor(vQ), thFr = fract(vQ);
float thH = hash12(vec2(thId, float(thTube) * 17.0 + 3.0));
float thAlong = snoise(vec2(thId * 0.37 + float(thTube) * 11.0, vU * uAlong));
float thRidge = sin(PI * thFr); // 0 in a groove, 1 on a fibre's crown
diffuseColor.rgb = uColors[thPi] * (1.0 + thDetail * (0.1 * (thH - 0.5) + 0.05 * thAlong - 0.06 * (1.0 - thRidge)));
// crevices where the plies press together (none where the fray has pulled them apart)
vec4 thC = uContact[thTube];
float thGap = min(th_angDist(vTh, thC.x) - thC.z, th_angDist(vTh, thC.y) - thC.w);
float thAO = mix(${glsl(THREAD_LOOK.creviceAO)}, 1.0, smoothstep(0.0, ${glsl(deg(THREAD_LOOK.creviceDeg))}, thGap));
thAO = mix(thAO, 1.0, sat(1.5 * vW));
`;

const PLY_FRAG_NORMAL = /* glsl */ `
float faceDirection = gl_FrontFacing ? 1.0 : - 1.0;
vec3 normal = normalize(vNormal);
vec3 nonPerturbedNormal = normal;
// along the fibres (thF) and across them (thX); the grooves tilt the normal across
vec3 thF = normalize(vFibre - dot(vFibre, normal) * normal);
vec3 thX = cross(normal, thF);
normal = normalize(normal + ${glsl(THREAD_LOOK.groove)} * (0.4 + 1.2 * thH) * thDetail * cos(PI * thFr) * thX);
thF = normalize(thF - dot(thF, normal) * normal);
thX = cross(normal, thF);
#ifdef USE_ANISOTROPY
  // three stretches the highlight along tbn[0]: across the fibres, as a fibre's micro-normals spread
  mat3 tbn = mat3(thX, thF, normal);
#endif
`;

const PLY_FRAG_EMISSIVE = /* glsl */ `
float thFacing = sat(dot(nonPerturbedNormal, normalize(vViewPosition)));
float thCore = mix(pow(thFacing, ${glsl(THREAD_LOOK.glowFalloff[0])}), pow(thFacing, ${glsl(THREAD_LOOK.glowFalloff[1])}), ${glsl(THREAD_LOOK.glowSoft)});
totalEmissiveRadiance += uGlow[thPi] * thCore * mix(0.35, 1.0, thAO) * (1.0 + 0.2 * thDetail * (thRidge - 0.6));
`;

const PLY_FRAG_SHEEN = /* glsl */ `
#ifdef USE_SHEEN
  material.sheenColor = mix(uColors[thPi], vec3(1.0), 0.15) * sheenColor;
#endif
`;

const PLY_FRAG_AO = /* glsl */ `
float thAOd = mix(1.0, thAO, 0.75); // direct light is only partly blocked by the neighbouring ply
reflectedLight.directDiffuse *= thAOd;
reflectedLight.directSpecular *= thAOd;
reflectedLight.indirectDiffuse *= thAO;
reflectedLight.indirectSpecular *= thAO;
#ifdef USE_SHEEN
  sheenSpecularDirect *= thAOd;
  sheenSpecularIndirect *= thAO;
#endif
`;

const FIBRE_VERT = /* glsl */ `
#include <common>
${VERT_PARS}
attribute vec4 aRoot;  // u, θ round the tube, tube, kind (0 fuzz, 1 fray fibre)
attribute vec4 aShape; // length (thread radii), lift at rest, extra lift at full fray (radians), curl
uniform vec2 uRes;
uniform float uFibreW;
varying float vSide;
varying float vHalfPx;
varying float vAlpha;
varying float vTube;
varying float vK;
varying vec3 vT;
varying vec3 vN0;
varying vec3 vPosV;
void main() {
  float t = position.x, side = position.y;
  vK = t;
  float u0 = aRoot.x, th = aRoot.y, kind = aRoot.w;
  vTube = aRoot.z;
  ThTube p = th_tube(u0, aRoot.z);
  float inWin = step(uDraw.x, u0) * step(u0, uDraw.y);
  float len = uR * aShape.x * p.tp * mix(1.0, p.w, kind) * inWin;
  if (len < 1e-6 * uR) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); vAlpha = 0.0; return; }
  vec3 off = cos(th) * p.N + sin(th) * p.B;
  vec3 root = p.P + p.rp * off;
  vec3 f0 = th_fibreDir(p, th);
  float lift = aShape.y + aShape.z * p.w;
  vec3 d0 = normalize(cos(lift) * f0 + sin(lift) * off);
  vec3 bend = aShape.w * normalize(cross(off, f0)) + 0.35 * sin(lift) * off; // curl sideways and away
  vec3 pos = root + len * (t * d0 + t * t * bend);
  vec3 tang = normalize(d0 + 2.0 * t * bend);
  vec4 mv = modelViewMatrix * vec4(pos, 1.0);
  vec4 clip = projectionMatrix * mv;
  vec4 clip2 = projectionMatrix * (modelViewMatrix * vec4(pos + tang * uR * 0.05, 1.0));
  vec2 s0 = clip.xy / clip.w * 0.5 * uRes, s1 = clip2.xy / clip2.w * 0.5 * uRes;
  vec2 dir = s1 - s0;
  dir = dot(dir, dir) > 1e-12 ? normalize(dir) : vec2(1.0, 0.0);
  // the fibre's true width in px, tapering to its tip; thinner than a pixel it fades instead
  float wpx = uFibreW * uR * projectionMatrix[1][1] * 0.5 * uRes.y / clip.w * (1.0 - 0.6 * t);
  vHalfPx = max(0.5 * wpx, 0.5);
  vAlpha = min(1.0, wpx);
  float ext = vHalfPx + 1.0;
  clip.xy += vec2(-dir.y, dir.x) * side * ext * 2.0 / uRes * clip.w;
  gl_Position = clip;
  vSide = side * ext;
  vT = normalize((modelViewMatrix * vec4(tang, 0.0)).xyz);
  vN0 = normalize((modelViewMatrix * vec4(off, 0.0)).xyz);
  vPosV = mv.xyz;
  // fuzz lying on the side that faces the camera only adds noise against its own ply: it reads on the silhouette
  vAlpha *= mix(1.0 - smoothstep(0.35, 0.8, dot(vN0, normalize(-mv.xyz))), 1.0, kind);
}
`;

const FIBRE_FRAG = /* glsl */ `
#include <common>
#include <lights_pars_begin>
uniform vec3 uColors[3];
uniform vec3 uGlow[3];
uniform float uTubePly[${MAX_TUBES}];
uniform float uFibreAmbient;
varying float vSide;
varying float vHalfPx;
varying float vAlpha;
varying float vTube;
varying float vK;
varying vec3 vT;
varying vec3 vN0;
varying vec3 vPosV;
// a fibre lit by one light: Kajiya-Kay diffuse and specular cone, and forward scatter when the light is behind it.
// The thread's body shades the fibre's root from lights on its far side; the free end sticks out into the light.
vec3 th_fibreLight(vec3 T, vec3 V, vec3 L, vec3 alb) {
  float TL = dot(T, L), TV = dot(T, V);
  float sTL = sqrt(max(0.0, 1.0 - TL * TL)), sTV = sqrt(max(0.0, 1.0 - TV * TV));
  float spec = pow(max(0.0, sTL * sTV - TL * TV), 48.0);
  float back = pow(max(0.0, -dot(L, V)), 3.0) * sTL;
  float vis = clamp(smoothstep(-0.3, 0.2, dot(vN0, L)) + 0.4 * vK, 0.0, 1.0);
  return vis * (alb * (0.15 * sTL + 0.4 * back) + vec3(0.1 * spec));
}
void main() {
  float cov = clamp(vHalfPx + 0.5 - abs(vSide), 0.0, 1.0) * vAlpha;
  if (cov < 0.02) discard;
  vec3 T = normalize(vT), V = normalize(-vPosV);
  int pi = int(uTubePly[int(vTube + 0.5)] + 0.5);
  vec3 alb = uColors[pi];
  vec3 col = alb * (uFibreAmbient + ambientLightColor);
  IncidentLight il;
#if NUM_DIR_LIGHTS > 0
  for (int i = 0; i < NUM_DIR_LIGHTS; i++) col += directionalLights[i].color * th_fibreLight(T, V, directionalLights[i].direction, alb);
#endif
#if NUM_POINT_LIGHTS > 0
  for (int i = 0; i < NUM_POINT_LIGHTS; i++) {
    getPointLightInfo(pointLights[i], vPosV, il);
    col += il.color * th_fibreLight(T, V, il.direction, alb);
  }
#endif
#if NUM_SPOT_LIGHTS > 0
  for (int i = 0; i < NUM_SPOT_LIGHTS; i++) {
    getSpotLightInfo(spotLights[i], vPosV, il);
    col += il.color * th_fibreLight(T, V, il.direction, alb);
  }
#endif
  col += 0.03 * uGlow[pi]; // fibres of a glowing ply carry a little of its core
  gl_FragColor = vec4(col, cov);
}
`;

// ------------------------------------------------------------------------------------------------ geometry

/** The tubes, one after another: vertices (u, θ, tube) on rings along the thread; the vertex shader places them. */
function tubeGeometry(tubes: number, rings: number, radial: number) {
  const perTube = (rings + 1) * (radial + 1);
  const pos = new Float32Array(tubes * perTube * 3);
  const idx = new Uint32Array(tubes * rings * radial * 6);
  let v = 0, e = 0;
  for (let p = 0; p < tubes; p++) {
    const base = p * perTube;
    for (let k = 0; k <= rings; k++) for (let j = 0; j <= radial; j++) {
      pos[v++] = k / rings;
      pos[v++] = (TAU * j) / radial;
      pos[v++] = p;
    }
    // outward-facing: (k, j) → (k, j + 1) → (k + 1, j) turns from round the tube to along it
    for (let k = 0; k < rings; k++) for (let j = 0; j < radial; j++) {
      const a = base + k * (radial + 1) + j, b = a + 1, c = a + radial + 1, d = c + 1;
      idx[e++] = a; idx[e++] = b; idx[e++] = c;
      idx[e++] = b; idx[e++] = d; idx[e++] = c;
    }
  }
  const g = new THREE.BufferGeometry();
  const at = new THREE.BufferAttribute(pos, 3);
  g.setAttribute('position', at);
  // three shades a mesh without normals flat; the shader builds the real normal, so `normal` shares position's buffer
  g.setAttribute('normal', at);
  g.setIndex(new THREE.BufferAttribute(idx, 1));
  return g;
}

interface FibreSpec { tubes: number; lengthOverR: number; contacts: [number, number, number, number][]; fuzz: number; seed: number }

/** Fibre ribbons: a strip template instanced per fibre, roots and shapes seeded (never Math.random). */
function fibreGeometry(s: FibreSpec) {
  const rnd = mulberry32(s.seed);
  const L = THREAD_LOOK;
  const perTube = (d: number) => Math.round(d * s.lengthOverR * s.fuzz);
  let nFuzz = perTube(L.fuzzDensity) * s.tubes, nFray = perTube(L.frayDensity) * s.tubes;
  const total = nFuzz + nFray;
  if (total > MAX_FIBRES) {
    nFuzz = Math.floor((nFuzz * MAX_FIBRES) / total);
    nFray = Math.floor((nFray * MAX_FIBRES) / total);
  }
  const n = nFuzz + nFray;
  if (n === 0) return null;
  const root = new Float32Array(n * 4), shape = new Float32Array(n * 4);
  for (let i = 0; i < n; i++) {
    const fray = i >= nFuzz, tube = i % s.tubes;
    // a root on the visible part of the tube, clear of the crevices (a few tries, then anywhere)
    const [c1, c2, h1, h2] = s.contacts[tube]!;
    let th = 0;
    for (let k = 0; k < 8; k++) {
      th = (rnd() * 2 - 1) * Math.PI;
      if (angDist(th, c1) > h1 + 0.35 && angDist(th, c2) > h2 + 0.35) break;
    }
    root[4 * i] = rnd();
    root[4 * i + 1] = th;
    root[4 * i + 2] = tube;
    root[4 * i + 3] = fray ? 1 : 0;
    const q = rnd();
    const [l0, l1] = fray ? L.frayLength : L.fuzzLength;
    shape[4 * i] = l0 + (l1 - l0) * (fray ? q : q * q); // fuzz is mostly short
    shape[4 * i + 1] = fray ? 0.15 : 0.05 + 0.45 * rnd() * rnd();
    shape[4 * i + 2] = fray ? 0.2 + 0.6 * rnd() : 0.5 + 0.6 * rnd();
    shape[4 * i + 3] = (rnd() * 2 - 1) * (fray ? 0.6 : 0.4);
  }
  const g = new THREE.InstancedBufferGeometry();
  const tpl = new Float32Array((FIBRE_SEGS + 1) * 2 * 3), ix: number[] = [];
  for (let k = 0; k <= FIBRE_SEGS; k++) for (let sd = 0; sd < 2; sd++) {
    const o = (2 * k + sd) * 3;
    tpl[o] = k / FIBRE_SEGS;
    tpl[o + 1] = sd ? 1 : -1;
  }
  for (let k = 0; k < FIBRE_SEGS; k++) {
    const a = 2 * k;
    ix.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
  }
  g.setAttribute('position', new THREE.BufferAttribute(tpl, 3));
  g.setIndex(ix);
  g.setAttribute('aRoot', new THREE.InstancedBufferAttribute(root, 4));
  g.setAttribute('aShape', new THREE.InstancedBufferAttribute(shape, 4));
  g.instanceCount = n;
  return g;
}

// ------------------------------------------------------------------------------------------------ centreline

/** Dense chords per output sample when measuring arc length (at least 2048 in all). */
const ARC_OVERSAMPLE = 4;
const arcChords = (M: number) => Math.max(ARC_OVERSAMPLE * (M - 1), 2048);

/**
 * Resample a centripetal Catmull-Rom through `points` at M points evenly spaced in arc length (into pos, float64),
 * returning its length. Arc length is measured on a dense polyline of arcChords(M) chords, held in `scratch` (reused
 * from call to call: setPoints runs every frame).
 */
function sampleArc(points: THREE.Vector3[], M: number, pos: Float64Array, scratch?: { P: Float64Array; S: Float64Array }): number {
  const curve = new THREE.CatmullRomCurve3(points, false, 'centripetal');
  const K = arcChords(M);
  const P = scratch?.P ?? new Float64Array((K + 1) * 3), S = scratch?.S ?? new Float64Array(K + 1);
  const q = new THREE.Vector3();
  for (let k = 0; k <= K; k++) {
    curve.getPoint(k / K, q);
    P[3 * k] = q.x; P[3 * k + 1] = q.y; P[3 * k + 2] = q.z;
    if (k) S[k] = S[k - 1]! + Math.hypot(q.x - P[3 * k - 3]!, q.y - P[3 * k - 2]!, q.z - P[3 * k - 1]!);
  }
  const L = S[K]!;
  let k = 0;
  for (let i = 0; i < M; i++) {
    const s = (i / (M - 1)) * L;
    while (k < K - 1 && S[k + 1]! < s) k++;
    const seg = S[k + 1]! - S[k]!;
    const f = seg > 0 ? clamp((s - S[k]!) / seg, 0, 1) : 0;
    for (let j = 0; j < 3; j++) pos[3 * i + j] = P[3 * k + j]! + (P[3 * (k + 1) + j]! - P[3 * k + j]!) * f;
  }
  return L;
}

/**
 * Tangents (central differences) and a rotation-minimising frame (double reflection, Wang et al. 2008) along the
 * samples, into the frame texture's four rows. The first normal is world up made square to the first tangent (world
 * +z when the thread starts nearly vertical).
 */
function writeFrames(pos: Float64Array, M: number, out: Float32Array) {
  const T = new Float64Array(M * 3), N = new Float64Array(M * 3);
  for (let i = 0; i < M; i++) {
    const a = Math.max(0, i - 1), b = Math.min(M - 1, i + 1);
    let x = pos[3 * b]! - pos[3 * a]!, y = pos[3 * b + 1]! - pos[3 * a + 1]!, z = pos[3 * b + 2]! - pos[3 * a + 2]!;
    const l = Math.hypot(x, y, z);
    if (l > 1e-12) { x /= l; y /= l; z /= l; } else if (i) { x = T[3 * i - 3]!; y = T[3 * i - 2]!; z = T[3 * i - 1]!; } else { x = 1; y = 0; z = 0; }
    T[3 * i] = x; T[3 * i + 1] = y; T[3 * i + 2] = z;
  }
  // first normal: up, or +z near vertical (blended, so it turns smoothly as the start swings toward vertical)
  const t0 = [T[0]!, T[1]!, T[2]!];
  const k = Math.min(1, Math.max(0, (Math.abs(t0[1]!) - 0.9) / 0.09));
  const ref = [0, 1 - k, k];
  const dr = ref[0]! * t0[0]! + ref[1]! * t0[1]! + ref[2]! * t0[2]!;
  let n0 = [ref[0]! - dr * t0[0]!, ref[1]! - dr * t0[1]!, ref[2]! - dr * t0[2]!];
  let ln = Math.hypot(n0[0]!, n0[1]!, n0[2]!);
  if (ln < 1e-9) { n0 = [1, 0, 0]; ln = 1; }
  N[0] = n0[0]! / ln; N[1] = n0[1]! / ln; N[2] = n0[2]! / ln;
  for (let i = 0; i < M - 1; i++) {
    const v1 = [pos[3 * i + 3]! - pos[3 * i]!, pos[3 * i + 4]! - pos[3 * i + 1]!, pos[3 * i + 5]! - pos[3 * i + 2]!];
    const c1 = v1[0]! ** 2 + v1[1]! ** 2 + v1[2]! ** 2;
    let r = [N[3 * i]!, N[3 * i + 1]!, N[3 * i + 2]!];
    if (c1 > 1e-24) {
      const ti = [T[3 * i]!, T[3 * i + 1]!, T[3 * i + 2]!];
      const vr = (2 / c1) * (v1[0]! * r[0]! + v1[1]! * r[1]! + v1[2]! * r[2]!);
      const vt = (2 / c1) * (v1[0]! * ti[0]! + v1[1]! * ti[1]! + v1[2]! * ti[2]!);
      const rL = [r[0]! - vr * v1[0]!, r[1]! - vr * v1[1]!, r[2]! - vr * v1[2]!];
      const tL = [ti[0]! - vt * v1[0]!, ti[1]! - vt * v1[1]!, ti[2]! - vt * v1[2]!];
      const v2 = [T[3 * i + 3]! - tL[0]!, T[3 * i + 4]! - tL[1]!, T[3 * i + 5]! - tL[2]!];
      const c2 = v2[0]! ** 2 + v2[1]! ** 2 + v2[2]! ** 2;
      const w2 = c2 > 1e-24 ? (2 / c2) * (v2[0]! * rL[0]! + v2[1]! * rL[1]! + v2[2]! * rL[2]!) : 0;
      r = [rL[0]! - w2 * v2[0]!, rL[1]! - w2 * v2[1]!, rL[2]! - w2 * v2[2]!];
    }
    // keep it exactly square to the next tangent and unit (no drift over thousands of steps)
    const tn = [T[3 * i + 3]!, T[3 * i + 4]!, T[3 * i + 5]!];
    const dt = r[0]! * tn[0]! + r[1]! * tn[1]! + r[2]! * tn[2]!;
    r = [r[0]! - dt * tn[0]!, r[1]! - dt * tn[1]!, r[2]! - dt * tn[2]!];
    const lr = Math.hypot(r[0]!, r[1]!, r[2]!) || 1;
    N[3 * i + 3] = r[0]! / lr; N[3 * i + 4] = r[1]! / lr; N[3 * i + 5] = r[2]! / lr;
  }
  for (let i = 0; i < M; i++) {
    const t = [T[3 * i]!, T[3 * i + 1]!, T[3 * i + 2]!], n = [N[3 * i]!, N[3 * i + 1]!, N[3 * i + 2]!];
    const b = [t[1]! * n[2]! - t[2]! * n[1]!, t[2]! * n[0]! - t[0]! * n[2]!, t[0]! * n[1]! - t[1]! * n[0]!];
    const rows = [[pos[3 * i]!, pos[3 * i + 1]!, pos[3 * i + 2]!], t, n, b];
    rows.forEach((v, row) => {
      const o = 4 * (row * M + i);
      out[o] = v[0]!; out[o + 1] = v[1]!; out[o + 2] = v[2]!; out[o + 3] = 0;
    });
  }
}

// ------------------------------------------------------------------------------------------------ Thread

export interface ThreadFrame { pos: THREE.Vector3; tangent: THREE.Vector3; normal: THREE.Vector3; binormal: THREE.Vector3 }

export class Thread {
  /** The plies; the fibres are its child. Add this to the stage's scene. */
  mesh: THREE.Mesh;
  /** The material's uniforms (shared by plies and fibres). */
  readonly uniforms: ThreadUniforms;
  /** The centreline the shaders read: M samples even in arc length × rows point, tangent, normal, binormal. */
  readonly frames: THREE.DataTexture;
  private readonly fibres: THREE.Mesh | null = null;
  private readonly R: number;
  private readonly tubes: Tube[];
  /** Public ply → its tube, or -1 for a 3-ply core (its centre is the axis). */
  private readonly plyTube: number[];
  private readonly colors: ThreadColor[];
  private readonly M: number;
  private readonly data: Float32Array;
  private readonly pos: Float64Array;
  private readonly arc: { P: Float64Array; S: Float64Array };
  private L = 0;
  private readonly L0: number;
  private draw: [number, number] = [0, 1];
  private fray = { at: 0.5, amount: 0, half: 1 };

  constructor(points: THREE.Vector3[], opts: ThreadOpts) {
    if (points.length < 2) throw new Error('Thread needs at least two points');
    if (!(opts.radius > 0)) throw new Error('Thread needs a radius > 0');
    const L = THREAD_LOOK;
    const R = (this.R = opts.radius);
    const n = opts.plies ?? 3;
    const cols = opts.colors?.length ? opts.colors : DEFAULT_COLORS;
    this.colors = Array.from({ length: n }, (_, i) => cols[i % cols.length]!);
    const core = opts.core ?? (n > 1 && this.colors[0] === 'bone' && this.colors.some((c) => c !== 'bone'));
    const lay = layout(n, core);
    const tubes = (this.tubes = lay.tubes);
    this.plyTube = this.colors.map((_, i) => (core && i === 0 ? -1 : tubes.findIndex((t) => t.ply === i)));
    // the length at construction sets the turns (material coordinates) and the ring count
    this.L0 = sampleArc(points, 2, new Float64Array(6));
    const twist = opts.twist ?? Math.tan(deg(lay.layDeg)) / (TAU * lay.layOffset * R);
    const turns = twist * this.L0;
    const rings = clamp(Math.round(opts.tubularSegments ?? Math.max(Math.ceil(turns * 24), Math.ceil((2 * this.L0) / R), 64)), 2, MAX_RINGS);
    const radial = Math.max(3, Math.round(opts.radialSegments ?? 16));
    this.M = rings + 1;
    this.pos = new Float64Array(this.M * 3);
    this.arc = { P: new Float64Array((arcChords(this.M) + 1) * 3), S: new Float64Array(arcChords(this.M) + 1) };
    this.data = new Float32Array(this.M * 16);
    this.frames = new THREE.DataTexture(this.data, this.M, 4, THREE.RGBAFormat, THREE.FloatType);
    this.frames.minFilter = this.frames.magFilter = THREE.NearestFilter;
    this.frames.generateMipmaps = false;

    // surface fibres: iso-lines of θ − K·u. K sets their angle on the ply's crown against the thread axis: a wound ply's
    // fibres lean from its own lay toward the axis (fibreLay); the core's sit at coreFibreDeg; a single strand's at its
    // twist (K = 0: the frame's own turn)
    const fibreK = (p: Tube) => {
      if (n === 1) return 0;
      const tanG = (1 - L.fibreLay) * TAU * p.d * R * twist;
      return (this.L0 * tanG - (p.d + p.r) * R * TAU * turns) / (p.r * R);
    };
    const cont = contacts(tubes);
    const col = (c: ThreadColor) => {
      const a = LIN[c], b = c === 'blood' ? LIN.bloodDim : c === 'moss' ? LIN.mossDim : a;
      return new THREE.Vector3(...a.map((x, k) => x + (b[k]! - x) * L.dye));
    };
    const slots = <T>(k: number, count: number, f: (i: number) => T) => Array.from({ length: k }, (_, i) => f(Math.min(i, count - 1)));
    this.uniforms = {
      tFrames: { value: this.frames },
      uM: { value: this.M },
      uR: { value: R },
      uTurns: { value: turns },
      uLen: { value: this.L0 },
      uTip: { value: L.tip * R },
      uDraw: { value: new THREE.Vector2(0, 1) },
      uFray: { value: new THREE.Vector3(0.5, 0, 1) },
      uTube: { value: slots(MAX_TUBES, tubes.length, (i) => new THREE.Vector4(tubes[i]!.r, tubes[i]!.d, tubes[i]!.phase, fibreK(tubes[i]!))) },
      uContact: { value: slots(MAX_TUBES, tubes.length, (i) => new THREE.Vector4(...cont[i]!)) },
      uTubePly: { value: slots(MAX_TUBES, tubes.length, (i) => tubes[i]!.ply) },
      uColors: { value: slots(3, n, (i) => col(this.colors[i]!)) },
      uGlow: { value: slots(3, n, () => new THREE.Vector3()) },
      uAlong: { value: (this.L0 / R) * 0.25 },
      uRes: { value: new THREE.Vector2(1920, 1080) },
    };
    this.setGlow(opts.glow ?? L.glow);
    this.setPoints(points);

    const mat = new THREE.MeshPhysicalMaterial({
      color: 0xffffff,
      roughness: L.roughness,
      metalness: 0,
      ior: L.ior,
      specularIntensity: L.specular,
      sheen: L.sheen,
      sheenRoughness: L.sheenRoughness,
      sheenColor: 0xffffff,
      anisotropy: L.anisotropy,
      anisotropyRotation: 0,
    });
    const u = this.uniforms;
    mat.onBeforeCompile = (shader) => {
      Object.assign(shader.uniforms, u);
      shader.vertexShader = shader.vertexShader
        .replace('#include <common>', `#include <common>\n${PLY_VERT_PARS}`)
        .replace('#include <beginnormal_vertex>', PLY_VERT_MAIN)
        .replace('#include <begin_vertex>', 'vec3 transformed = thPos;');
      shader.fragmentShader = shader.fragmentShader
        .replace('#include <common>', `#include <common>\n${PLY_FRAG_PARS}`)
        .replace('#include <color_fragment>', `#include <color_fragment>\n${PLY_FRAG_COLOR}`)
        .replace('#include <normal_fragment_begin>', PLY_FRAG_NORMAL)
        .replace('#include <emissivemap_fragment>', `#include <emissivemap_fragment>\n${PLY_FRAG_EMISSIVE}`)
        .replace('#include <lights_physical_fragment>', `#include <lights_physical_fragment>\n${PLY_FRAG_SHEEN}`)
        .replace('#include <aomap_fragment>', `#include <aomap_fragment>\n${PLY_FRAG_AO}`);
    };
    mat.customProgramCacheKey = () => 'thread3d-ply-4';
    this.mesh = new THREE.Mesh(tubeGeometry(tubes.length, rings, radial), mat);
    this.mesh.frustumCulled = false; // the geometry is built in the shader: its attributes are no bounds

    const fg = fibreGeometry({ tubes: tubes.length, lengthOverR: this.L0 / R, contacts: cont, fuzz: opts.fuzz ?? 1, seed: opts.seed ?? 0x7f4a7c15 });
    if (fg) {
      const fm = new THREE.ShaderMaterial({
        uniforms: { ...THREE.UniformsUtils.clone(THREE.UniformsLib.lights), ...u, uFibreW: { value: L.fibreWidth }, uFibreAmbient: { value: 0.04 } },
        vertexShader: FIBRE_VERT,
        fragmentShader: FIBRE_FRAG,
        lights: true,
        transparent: true,
        depthWrite: true, // the DoF reads their depth: fibres by a sharp thread stay sharp
        side: THREE.DoubleSide,
      });
      this.fibres = new THREE.Mesh(fg, fm);
      this.fibres.frustumCulled = false;
      this.fibres.onBeforeRender = (renderer) => {
        const rt = renderer.getRenderTarget();
        if (rt) u.uRes.value.set(rt.width, rt.height);
        else renderer.getDrawingBufferSize(u.uRes.value);
      };
      this.mesh.add(this.fibres);
    }
  }

  /** Move the thread: a new Catmull-Rom through `points`. The plies keep their place in the thread (material u). */
  setPoints(points: THREE.Vector3[]) {
    if (points.length < 2) throw new Error('Thread needs at least two points');
    this.L = sampleArc(points, this.M, this.pos, this.arc);
    writeFrames(this.pos, this.M, this.data);
    this.frames.needsUpdate = true;
    this.uniforms.uLen.value = Math.max(this.L, 1e-9);
  }

  /** Show the arc-length window [p0, p1] (fractions of the length): draw on with p1, retract with p0. The ends taper. */
  setDraw(p0: number, p1: number) {
    const a = clamp(p0, 0, 1), b = clamp(p1, 0, 1);
    this.draw = [a, b];
    this.uniforms.uDraw.value.set(a, b);
    this.mesh.visible = b > a;
  }

  /**
   * Fray around arc fraction `at`: the wound plies stand apart, swell and untwist over `span` either side (world
   * units, default THREAD_LOOK.fraySpan radii), and the fray fibres grow and lift. `amount` 0..1. The twist taken out
   * moves to the shoulders, so the thread beyond them doesn't turn.
   */
  setFray(at: number, amount: number, span = THREAD_LOOK.fraySpan * this.R) {
    this.fray = { at, amount: clamp(amount, 0, 1), half: Math.max(span, 1e-9) / this.L0 };
    this.uniforms.uFray.value.set(this.fray.at, this.fray.amount, this.fray.half);
  }

  /** Emissive level of the blood and moss cores (look.ts glow level); bone stays dark whatever the level. */
  setGlow(level: number) {
    this.uniforms.uGlow.value.forEach((g, i) => {
      const key = i < this.colors.length ? GLOW_KEY[this.colors[i]!] : null;
      if (key && level > 0) g.set(...glowLevel(key, level));
      else g.set(0, 0, 0);
    });
  }

  /** Arc length now. */
  length() {
    return this.L;
  }

  /** The centreline at arc fraction u. */
  pointAt(u: number, target = new THREE.Vector3()) {
    return target.copy(this.frameAt(u).pos);
  }

  /** The centreline and its rotation-minimising frame at arc fraction u (as the shaders read it). */
  frameAt(u: number): ThreadFrame {
    const M = this.M, d = this.data;
    const s = clamp(u, 0, 1) * (M - 1);
    const i0 = Math.min(Math.floor(s), M - 2), f = s - i0;
    const row = (r: number) => {
      const a = 4 * (r * M + i0), b = a + 4;
      return new THREE.Vector3(d[a]! + (d[b]! - d[a]!) * f, d[a + 1]! + (d[b + 1]! - d[a + 1]!) * f, d[a + 2]! + (d[b + 2]! - d[a + 2]!) * f);
    };
    const pos = row(0), tangent = row(1).normalize(), n = row(2);
    const normal = n.sub(tangent.clone().multiplyScalar(n.dot(tangent))).normalize();
    return { pos, tangent, normal, binormal: new THREE.Vector3().crossVectors(tangent, normal) };
  }

  /**
   * Centre of ply `ply` at arc fraction u, as the vertex shader places it (window taper and fray included). A 3-ply
   * core's centre is the axis.
   */
  plyCentre(u: number, ply: number, target = new THREE.Vector3()) {
    const ti = this.plyTube[clamp(Math.round(ply), 0, this.plyTube.length - 1)]!;
    if (ti < 0) return this.pointAt(u, target);
    const p = this.tubes[ti]!;
    const [p0, p1] = this.draw;
    u = clamp(u, p0, p1);
    const x = clamp((Math.min(u - p0, p1 - u) * this.uniforms.uLen.value) / this.uniforms.uTip.value, 0, 1);
    const tp = 1 - (1 - x) * (1 - x);
    const { pos, normal, binormal } = this.frameAt(u);
    const { at, amount } = this.fray, h = Math.max(this.fray.half, 1e-6), y = u - at;
    const w = amount * bump(y / h);
    const turns = this.uniforms.uTurns.value * (u - THREAD_LOOK.frayUntwist * amount * h * (bumpInt(y / h) - bumpInt(y / (3 * h))));
    const phi = TAU * (turns + p.phase);
    const d = this.R * p.d * (1 + THREAD_LOOK.fraySeparation * w) * (tp + (1 - tp) * w);
    return target.copy(pos).addScaledVector(normal, d * Math.cos(phi)).addScaledVector(binormal, d * Math.sin(phi));
  }

  dispose() {
    this.mesh.geometry.dispose();
    (this.mesh.material as THREE.Material).dispose();
    if (this.fibres) {
      this.fibres.geometry.dispose();
      (this.fibres.material as THREE.Material).dispose();
    }
    this.frames.dispose();
  }
}
