// The Memory Graph of scene `anywhere` (Plan 2 Task 24), recreated from the console (gitloom web/src/app/Graph.tsx):
// every node a memory or a directory, tiers settling into their own regions round the centre, faint structural lines
// from each node to its parent, green lines for learned relations.
//
// The layout is the console's own force simulation (repulsion, springs to the parent and along relations, a pull toward
// the tier's direction, damping, the heat `alpha` cooling 1.5% a tick, four steps a tick for the first forty then two),
// run once in init from seeded starting places, every tick's positions kept. So the graph is a pure function of time:
// the scene maps its time to a fractional tick and reads the two ticks either side. It starts packed at the centre (the
// console reheats from its tier directions; the film starts it tighter, so the settle reads as a burst that sorts
// itself into four regions).
//
// Drawn on the GPU over the card's face in its px (y down from its top edge): edges as instanced quads with an
// anti-aliased line in the fragment shader, nodes as instanced quads with a disc or a ring. Colours are the palette's:
// a memory file in one of blood's three shades by its content (the console hashes into a band round blood), a section
// in blood's dim shade and smaller, a directory a ring; relations moss, lit when they draw on.
import * as THREE from 'three';
import { LIN } from '../engine/palette';
import { glow } from '../engine/look';
import { hash } from '../engine/util';
import { OVER } from '../engine/panel-light';

export type Kind = 'dir' | 'file' | 'section';
export interface GNode {
  path: string;
  tier: string;
  kind: Kind;
}
export interface GEdge {
  src: string;
  dst: string;
}

/** The four tiers, sorted as the console sorts them (each its direction from the centre, the first straight up). */
export const TIERS = ['facts', 'incidents', 'rules', 'skills'] as const;

// ------------------------------------------------------------------------------------------------ the memory

/** A file and its sections (names only: the graph labels directories). */
type F = [path: string, sections?: number];

/**
 * The memory the card draws: the tiers, facts' folders, the memories the film has met (user.md, maya.md, acme.md, the
 * Lisbon trip and its hotel and city, the camera) and others like them, with sections. Paths are data, never shown.
 */
const FILES: F[] = [
  ['facts/people/user.md', 2], ['facts/people/maya.md', 1], ['facts/people/sam.md'], ['facts/people/priya.md', 1],
  ['facts/orgs/acme.md', 2], ['facts/orgs/initech.md'],
  ['facts/trips/lisbon-2026.md', 2], ['facts/trips/hotel.md', 1], ['facts/trips/city.md'],
  ['facts/camera-gear/sony-a7iii-purchase-42065a87.md', 1], ['facts/camera-gear/lenses.md'],
  ['facts/stack.md', 2], ['facts/editor.md'],
  ['incidents/2026-07-30-deploy.md', 1], ['incidents/2026-08-02-flaky-test.md'], ['incidents/2026-08-11-oom.md', 2],
  ['incidents/2026-08-19-dns.md'], ['incidents/2026-09-03-migration.md', 1],
  ['rules/commits.md', 2], ['rules/reviews.md', 1], ['rules/secrets.md'], ['rules/style.md', 1],
  ['skills/release.md', 2], ['skills/bisect.md', 1], ['skills/profiling.md'], ['skills/k8s-rollout.md', 1],
];

/** Learned relations (wikilinks): the film's own, user.md to acme.md, maya.md to the trip and on to hotel and city. */
const RELATIONS: [string, string][] = [
  ['facts/people/user.md', 'facts/orgs/acme.md'],
  ['facts/people/maya.md', 'facts/trips/lisbon-2026.md'],
  ['facts/trips/lisbon-2026.md', 'facts/trips/hotel.md'],
  ['facts/trips/hotel.md', 'facts/trips/city.md'],
  ['facts/people/user.md', 'facts/editor.md'],
  ['incidents/2026-08-11-oom.md', 'skills/profiling.md'],
  ['incidents/2026-07-30-deploy.md', 'rules/commits.md'],
  ['skills/k8s-rollout.md', 'facts/stack.md'],
  ['rules/reviews.md', 'facts/people/priya.md'],
  ['skills/release.md', 'rules/commits.md'],
];

export function parentOf(path: string): string | null {
  const h = path.indexOf('#');
  if (h > 0) return path.slice(0, h);
  const s = path.lastIndexOf('/');
  return s > 0 ? path.slice(0, s) : null;
}

/** The memory as the console's graph endpoint returns it: nodes (directories, files, sections) and relations. */
export function memoryGraph(): { nodes: GNode[]; edges: GEdge[] } {
  const nodes: GNode[] = [];
  const seen = new Set<string>();
  const add = (path: string, kind: Kind) => {
    if (seen.has(path)) return;
    seen.add(path);
    nodes.push({ path, tier: path.split('/')[0]!.split('#')[0]!, kind });
  };
  for (const t of TIERS) add(t, 'dir');
  for (const [path, sections = 0] of FILES) {
    const parts = path.split('/');
    for (let i = 1; i < parts.length - 1; i++) add(parts.slice(0, i + 1).join('/'), 'dir');
    add(path, 'file');
    for (let s = 0; s < sections; s++) add(`${path}#s${s + 1}`, 'section');
  }
  return { nodes, edges: RELATIONS.map(([src, dst]) => ({ src, dst })) };
}

// ------------------------------------------------------------------------------------------------ the simulation

/** The console's constants (Graph.tsx), and the film's tighter start. */
export const SIM = {
  repel: 340, cutoff: 32000, parentRest: 42, relationRest: 110, spring: 0.02,
  tierR: 170, gravX: 0.0018, gravY: 0.0016, damping: 0.86, cool: 0.985,
  /** Ticks of four steps before the rest take two (the console's warm start). */
  warm: 40,
  /** Where nodes start: an even disc this wide (sim px; a sunflower spiral, tiers mixed through it). */
  startR: 150,
} as const;

export interface Sim {
  nodes: GNode[];
  /** Node index pairs: structure (child, parent) and relations. */
  structure: [number, number][];
  relations: [number, number][];
  /** Positions per tick: ticks[k][2i], ticks[k][2i + 1] (sim px, y down, about the centre). */
  ticks: Float32Array[];
  /** Each node's radius (sim px). */
  r: Float32Array;
}

/** The tier's direction from the centre (radians, y down: the first tier straight up). */
export const tierAngle = (tier: string) => {
  const i = Math.max(0, (TIERS as readonly string[]).indexOf(tier));
  return (2 * Math.PI * i) / TIERS.length - Math.PI / 2;
};

/**
 * Run the console's simulation for `n` ticks from the film's start and keep every tick (tick 0 is the start). Pure:
 * the same memory gives the same ticks.
 */
export function simulate(g: { nodes: GNode[]; edges: GEdge[] }, n: number): Sim {
  const N = g.nodes.length;
  const index = new Map(g.nodes.map((nd, i) => [nd.path, i]));
  const x = new Float64Array(N), y = new Float64Array(N), vx = new Float64Array(N), vy = new Float64Array(N);
  const ta = new Float64Array(N), r = new Float32Array(N);
  // the start: an even disc (a sunflower spiral, so no two start on top of each other and nothing is flung), each tier
  // dealt the places nearest its own direction (its sector of the disc), in a seeded order within it; the layout opens
  // the disc out into the four regions
  const GOLDEN = Math.PI * (3 - Math.sqrt(5));
  const slots = Array.from({ length: N }, (_, k) => ({ r: SIM.startR * Math.sqrt((k + 0.5) / N), a: k * GOLDEN, taken: false }));
  const gap = (a: number, b: number) => Math.abs(Math.atan2(Math.sin(a - b), Math.cos(a - b)));
  for (const tier of TIERS) {
    const want = tierAngle(tier);
    // its members in path order (a folder, its files, each file's sections), dealt its places in angle order across
    // its sector, so what is linked starts near what it is linked to
    const members = g.nodes.map((nd, i) => (nd.tier === tier ? i : -1)).filter((i) => i >= 0)
      .sort((a, b) => (g.nodes[a]!.path < g.nodes[b]!.path ? -1 : g.nodes[a]!.path > g.nodes[b]!.path ? 1 : 0));
    const signed = (a: number) => Math.atan2(Math.sin(a - want), Math.cos(a - want));
    const free = slots.map((sl, k) => k).filter((k) => !slots[k]!.taken).sort((a, b) => gap(slots[a]!.a, want) - gap(slots[b]!.a, want) || a - b)
      .slice(0, members.length).sort((a, b) => signed(slots[a]!.a) - signed(slots[b]!.a) || slots[a]!.r - slots[b]!.r);
    members.forEach((i, m) => {
      const sl = slots[free[m]!]!;
      sl.taken = true;
      x[i] = sl.r * Math.cos(sl.a);
      y[i] = sl.r * Math.sin(sl.a);
    });
  }
  g.nodes.forEach((nd, i) => {
    ta[i] = tierAngle(nd.tier);
    r[i] = nd.kind === 'dir' ? 8 : nd.kind === 'file' ? 5.5 : 3.5;
  });
  const springs: [number, number, number][] = [];
  const structure: [number, number][] = [], relations: [number, number][] = [];
  g.nodes.forEach((nd, i) => {
    const p = parentOf(nd.path);
    const j = p === null ? undefined : index.get(p);
    if (j !== undefined) {
      springs.push([i, j, SIM.parentRest]);
      structure.push([i, j]);
    }
  });
  for (const e of g.edges) {
    const a = index.get(e.src), b = index.get(e.dst);
    if (a === undefined || b === undefined) throw new Error(`anywhere-graph: a relation to a node it lacks (${e.src} → ${e.dst})`);
    springs.push([a, b, SIM.relationRest]);
    relations.push([a, b]);
  }
  const step = (alpha: number) => {
    for (let i = 0; i < N; i++) {
      for (let j = i + 1; j < N; j++) {
        let dx = x[i]! - x[j]!, dy = y[i]! - y[j]!;
        const d2 = dx * dx + dy * dy + 0.01;
        if (d2 > SIM.cutoff) continue;
        const f = (SIM.repel / d2) * alpha, d = Math.sqrt(d2);
        dx /= d;
        dy /= d;
        vx[i] += dx * f; vy[i] += dy * f;
        vx[j] -= dx * f; vy[j] -= dy * f;
      }
    }
    for (const [a, b, rest] of springs) {
      const dx = x[b]! - x[a]!, dy = y[b]! - y[a]!;
      const d = Math.sqrt(dx * dx + dy * dy) + 0.01, f = (d - rest) * SIM.spring * alpha;
      vx[a] += (dx / d) * f; vy[a] += (dy / d) * f;
      vx[b] -= (dx / d) * f; vy[b] -= (dy / d) * f;
    }
    for (let i = 0; i < N; i++) {
      vx[i] += (Math.cos(ta[i]!) * SIM.tierR - x[i]!) * SIM.gravX * alpha;
      vy[i] += (Math.sin(ta[i]!) * SIM.tierR - y[i]!) * SIM.gravY * alpha;
      vx[i] *= SIM.damping;
      vy[i] *= SIM.damping;
      x[i] += vx[i]!;
      y[i] += vy[i]!;
    }
  };
  const snap = () => {
    const p = new Float32Array(2 * N);
    for (let i = 0; i < N; i++) (p[2 * i] = x[i]!), (p[2 * i + 1] = y[i]!);
    return p;
  };
  const ticks = [snap()];
  let alpha = 1;
  for (let k = 0; k < n; k++) {
    const steps = k < SIM.warm ? 4 : 2;
    for (let s = 0; s < steps; s++) step(alpha);
    alpha *= SIM.cool;
    ticks.push(snap());
  }
  return { nodes: g.nodes, structure, relations, ticks, r };
}

/** Node i's place at a fractional tick (linear between the two ticks either side; held past the last). */
export function placeAt(sim: Sim, tick: number, i: number, out: { x: number; y: number } = { x: 0, y: 0 }) {
  const last = sim.ticks.length - 1;
  const k = Math.max(0, Math.min(last, tick)), k0 = Math.floor(k), k1 = Math.min(last, k0 + 1), u = k - k0;
  const a = sim.ticks[k0]!, b = sim.ticks[k1]!;
  out.x = a[2 * i]! + (b[2 * i]! - a[2 * i]!) * u;
  out.y = a[2 * i + 1]! + (b[2 * i + 1]! - a[2 * i + 1]!) * u;
  return out;
}

/** The box the settled graph spans (sim px, radii included): what the card's view fits. */
export function boundsOf(sim: Sim, tick = sim.ticks.length - 1) {
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  const p = { x: 0, y: 0 };
  for (let i = 0; i < sim.nodes.length; i++) {
    placeAt(sim, tick, i, p);
    const r = sim.r[i]!;
    x0 = Math.min(x0, p.x - r); x1 = Math.max(x1, p.x + r); y0 = Math.min(y0, p.y - r); y1 = Math.max(y1, p.y + r);
  }
  return { x0, x1, y0, y1 };
}

// ------------------------------------------------------------------------------------------------ the drawing

const QUAD_VERT_HEAD = /* glsl */ `
  precision highp float;
  uniform mat4 projectionMatrix, modelViewMatrix;
  in vec2 corner;
  out vec2 vP;
`;

/** Edges: a quad round each segment (its width plus a px of anti-aliasing each side), the line's coverage in the
 * fragment shader. Per instance: the two ends (card px), the width (px), a linear colour and its alpha. */
const EDGE_VERT = /* glsl */ `${QUAD_VERT_HEAD}
  in vec4 aEnds;
  in float aWidth;
  in vec4 aColor;
  uniform vec2 uSize;
  uniform float uLift;
  out vec4 vColor;
  out float vHalf, vLen;
  void main() {
    vec2 a = aEnds.xy, b = aEnds.zw, d = b - a;
    float len = max(length(d), 1e-4);
    vec2 t = d / len, n = vec2(-t.y, t.x);
    float h = 0.5 * aWidth + 1.5;
    // the quad in the segment's frame: x along it (past each end by h), y across it
    vec2 q = vec2(mix(-h, len + h, corner.x), mix(-h, h, corner.y));
    vec2 px = a + t * q.x + n * q.y;
    vP = q;
    vHalf = 0.5 * aWidth;
    vLen = len;
    vColor = aColor;
    if (aColor.a <= 0.0) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); return; }
    vec3 pos = vec3((px.x - 0.5 * uSize.x) / 1000.0, (0.5 * uSize.y - px.y) / 1000.0, uLift / 1000.0);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
  }`;

const EDGE_FRAG = /* glsl */ `
  precision highp float;
  in vec2 vP;
  in vec4 vColor;
  in float vHalf, vLen;
  out vec4 fragColor;
  void main() {
    float along = clamp(vP.x, 0.0, vLen);
    float d = length(vec2(vP.x - along, vP.y)) - vHalf;
    float aa = max(fwidth(d), 1e-4);
    float c = clamp(0.5 - d / aa, 0.0, 1.0) * vColor.a;
    if (c <= 0.002) discard;
    fragColor = vec4(vColor.rgb * c, c);
  }`;

/** Nodes: a quad round each, a disc (kind 0) or a ring with a dark fill (kind 1). Per instance: centre (px), radius, kind;
 * a linear colour and alpha; the ring's fill colour. */
const NODE_VERT = /* glsl */ `${QUAD_VERT_HEAD}
  in vec4 aNode;   // x, y, r, kind
  in vec4 aColor;
  uniform vec2 uSize;
  uniform float uLift;
  out vec4 vColor;
  out vec2 vRK;
  void main() {
    float h = aNode.z + 2.0;
    vec2 q = (corner * 2.0 - 1.0) * h;
    vP = q;
    vRK = aNode.zw;
    vColor = aColor;
    if (aColor.a <= 0.0 || aNode.z <= 0.0) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); return; }
    vec2 px = aNode.xy + q;
    vec3 pos = vec3((px.x - 0.5 * uSize.x) / 1000.0, (0.5 * uSize.y - px.y) / 1000.0, (uLift + 0.05) / 1000.0);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);

  }`;

const NODE_FRAG = /* glsl */ `
  precision highp float;
  uniform vec3 uFill;
  in vec2 vP;
  in vec4 vColor;
  in vec2 vRK;
  out vec4 fragColor;
  void main() {
    float r = vRK.x, d = length(vP) - r;
    float aa = max(fwidth(d), 1e-4);
    float cov = clamp(0.5 - d / aa, 0.0, 1.0) * vColor.a;
    if (cov <= 0.002) discard;
    vec3 col = vColor.rgb;
    if (vRK.y > 0.5) {
      // a directory: a ring 2 px wide round a dark fill
      float ring = clamp(0.5 - (abs(d + 1.0) - 1.0) / aa, 0.0, 1.0);
      col = mix(uFill, vColor.rgb, ring);
    } else {
      // a memory: lit a little from the upper left, a bead of colour rather than a flat dot
      vec2 l = vP / max(r, 1e-3);
      col *= 0.82 + 0.3 * clamp(1.0 - length(l - vec2(-0.35, -0.4)), 0.0, 1.0);
    }
    fragColor = vec4(col * cov, cov);
  }`;

function premultMaterial(vert: string, frag: string, uniforms: Record<string, THREE.IUniform>) {
  const m = new THREE.RawShaderMaterial({ glslVersion: THREE.GLSL3, uniforms, vertexShader: vert, fragmentShader: frag, transparent: true, depthWrite: false, side: THREE.DoubleSide });
  m.blending = THREE.CustomBlending;
  m.blendEquation = THREE.AddEquation;
  m.blendSrc = THREE.OneFactor;
  m.blendDst = THREE.OneMinusSrcAlphaFactor;
  m.blendSrcAlpha = THREE.OneFactor;
  m.blendDstAlpha = THREE.OneMinusSrcAlphaFactor;
  return m;
}

function instanced(count: number, attrs: [string, number][]) {
  const g = new THREE.InstancedBufferGeometry();
  g.setAttribute('corner', new THREE.BufferAttribute(new Float32Array([0, 0, 1, 0, 1, 1, 0, 1]), 2));
  g.setIndex([0, 1, 2, 0, 2, 3]);
  const bufs: Record<string, THREE.InstancedBufferAttribute> = {};
  for (const [name, size] of attrs) {
    const a = new THREE.InstancedBufferAttribute(new Float32Array(count * size), size);
    a.setUsage(THREE.DynamicDrawUsage);
    g.setAttribute(name, a);
    bufs[name] = a;
  }
  g.instanceCount = count;
  return { g, bufs };
}

/** A file's shade of blood, by its content (the console hashes each memory into a band round blood). */
function fileColor(path: string): readonly [number, number, number] {
  const h = hash(path.length, path.charCodeAt(path.length - 4) ?? 0, path.charCodeAt(6) ?? 0, path.charCodeAt(2) ?? 0);
  return h < 0.42 ? LIN.blood : h < 0.74 ? LIN.bloodBright : LIN.bloodDim;
}

export interface GraphLook {
  /** 0..1: the whole graph's strength (it fades in with its card). */
  alpha: number;
  /** 0..1 each: how far each relation has drawn on, and its light (0: the console's moss, 1: lit to a glow). */
  draw: (rel: number) => number;
  lit: (rel: number) => number;
}

/** The graph over a card's face: `area` is where it fits (card px), `size` the card's (for the mesh's frame). */
export class GraphView {
  group = new THREE.Group();
  private edges: ReturnType<typeof instanced>;
  private nodes: ReturnType<typeof instanced>;
  private edgeMat: THREE.RawShaderMaterial;
  private nodeMat: THREE.RawShaderMaterial;
  private colors: (readonly [number, number, number])[];
  /** sim px → card px: scale and centre. */
  readonly k: number;
  readonly cx: number;
  readonly cy: number;
  private p = { x: 0, y: 0 };
  private q = { x: 0, y: 0 };

  constructor(readonly sim: Sim, size: { w: number; h: number }, area: { x0: number; y0: number; x1: number; y1: number }, margin = 14) {
    const b = boundsOf(sim);
    this.k = Math.min((area.x1 - area.x0 - 2 * margin) / (b.x1 - b.x0), (area.y1 - area.y0 - 2 * margin) / (b.y1 - b.y0));
    this.cx = (area.x0 + area.x1) / 2 - ((b.x0 + b.x1) / 2) * this.k;
    this.cy = (area.y0 + area.y1) / 2 - ((b.y0 + b.y1) / 2) * this.k;
    const nE = sim.structure.length + sim.relations.length, nN = sim.nodes.length;
    this.edges = instanced(nE, [['aEnds', 4], ['aWidth', 1], ['aColor', 4]]);
    this.nodes = instanced(nN, [['aNode', 4], ['aColor', 4]]);
    const sizeU = { value: new THREE.Vector2(size.w, size.h) };
    this.edgeMat = premultMaterial(EDGE_VERT, EDGE_FRAG, { uSize: sizeU, uLift: { value: 0.3 } });
    this.nodeMat = premultMaterial(NODE_VERT, NODE_FRAG, { uSize: sizeU, uLift: { value: 0.3 }, uFill: { value: new THREE.Vector3(...LIN.ink2) } });
    const em = new THREE.Mesh(this.edges.g, this.edgeMat), nm = new THREE.Mesh(this.nodes.g, this.nodeMat);
    em.renderOrder = OVER;
    nm.renderOrder = OVER + 1;
    em.frustumCulled = nm.frustumCulled = false;
    this.group.add(em, nm);
    this.colors = sim.nodes.map((nd) => (nd.kind === 'dir' ? LIN.boneFaint : nd.kind === 'section' ? LIN.bloodDim : fileColor(nd.path)));
  }

  /** Node i's place on the card (px) at a fractional tick. */
  at(tick: number, i: number, out = { x: 0, y: 0 }) {
    placeAt(this.sim, tick, i, out);
    out.x = this.cx + out.x * this.k;
    out.y = this.cy + out.y * this.k;
    return out;
  }

  /** Pose everything for a fractional tick. */
  set(tick: number, look: GraphLook) {
    const { sim, k } = this, A = look.alpha;
    this.group.visible = A > 0.002;
    if (!this.group.visible) return;
    const E = this.edges.bufs, Nd = this.nodes.bufs;
    const ends = E.aEnds!.array as Float32Array, width = E.aWidth!.array as Float32Array, ecol = E.aColor!.array as Float32Array;
    let e = 0;
    // structure: faint hairlines (the console's ruleStrong at 55%)
    for (const [a, b] of sim.structure) {
      this.at(tick, a, this.p);
      this.at(tick, b, this.q);
      ends.set([this.p.x, this.p.y, this.q.x, this.q.y], 4 * e);
      width[e] = 1;
      ecol.set([...LIN.boneFaint, 0.42 * A], 4 * e);
      e++;
    }
    // relations: moss, drawn on from their source, lit as they draw
    const moss = LIN.moss, mossGlow = glow('moss', 1.6);
    sim.relations.forEach(([a, b], r) => {
      const d = look.draw(r), lit = look.lit(r);
      this.at(tick, a, this.p);
      this.at(tick, b, this.q);
      const x1 = this.p.x + (this.q.x - this.p.x) * d, y1 = this.p.y + (this.q.y - this.p.y) * d;
      ends.set([this.p.x, this.p.y, x1, y1], 4 * e);
      width[e] = 1.5 + 0.6 * lit;
      const c = [0, 1, 2].map((j) => moss[j]! + (mossGlow[j]! - moss[j]!) * lit);
      ecol.set([c[0]!, c[1]!, c[2]!, d > 0.002 ? (0.68 + 0.32 * lit) * A : 0], 4 * e);
      e++;
    });
    const node = Nd.aNode!.array as Float32Array, ncol = Nd.aColor!.array as Float32Array;
    sim.nodes.forEach((nd, i) => {
      this.at(tick, i, this.p);
      node.set([this.p.x, this.p.y, sim.r[i]! * Math.max(0.75, Math.min(1.3, k)), nd.kind === 'dir' ? 1 : 0], 4 * i);
      const c = this.colors[i]!;
      ncol.set([c[0], c[1], c[2], A], 4 * i);
    });
    for (const a of [...Object.values(E), ...Object.values(Nd)]) a.needsUpdate = true;
  }

  dispose() {
    this.edges.g.dispose();
    this.nodes.g.dispose();
    this.edgeMat.dispose();
    this.nodeMat.dispose();
  }
}
