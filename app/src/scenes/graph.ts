// Scene 10 `graph`: "I connect the dots... and I learn your language." (Plan 2 Task 20; spec §4 10.) Memories link to
// each other: a wikilink is an edge, a link to a file not yet written heals when it is, a walk follows the edges, and a
// word she's been taught finds the memory that spells it the long way.
//
// One world, one camera, every time from the data (her measured onsets, the score's beats; graph-time.ts):
// 1. The link. In close on the file's last line, `Works with [[facts/orgs/acme.md]].`, a diff thread draws on under the
//    link and tightens. On "I", on the downbeat, it lifts off the page and races out into the dark, the camera pulling
//    back and round after it, and lands in the acme.md bead on the eighth: the edge. Moss light runs back down it to
//    the link.
// 2. The dots. The camera opens out on the constellation: memories as glass beads, a pearl at each one's heart, threads
//    from pearl to pearl, the graph going on into the dark. A new memory, maya.md, throws a thread toward
//    [[facts/trips/lisbon-2026.md]], a file that doesn't exist yet: it falls short and dangles, blood dashes running down
//    it, pinging on the beat, unanswered.
// 3. The heal. On the beat after "dots…" the trip is written: its bead drops in where the link pointed, the loose end
//    snaps up onto it and the dashes close up, blood turning moss, the tag becoming the trip's name. The moss runs on:
//    the walk, a hop a sixteenth, trip, hotel, city, the camera pulling back to keep up with it.
// 4. The vocabulary. As the walk lands a terminal rises into the foreground and `gitloom vocab add --term kubernetes
//    --alias k8s` types in with "and I learn"; on the downbeat its answer, `k8s → kubernetes  ·  search finds either
//    form`, the arrow in moss.
// 5. The search. On "your" `k8s` lifts off the answer as a thread, the link's rhyme, and searches up into the graph, the
//    camera going with it; on the beat inside "language." it lands in acme.md, and the word that memory says the long
//    way, kubernetes, lights under its name.
import * as THREE from 'three';
import { Scene, disposeLayer, type Frame, type PostOverrides } from '../engine/scene';
import { CameraRig, Stage, freeTransmission, initAreaLights, type CamKey } from '../engine/stage';
import { H, Layer2D, W, makeRT } from '../engine/gl';
import { Panel, panelLayout, type PanelLine } from '../engine/panels';
import { Halo } from '../engine/panel-light';
import { DIFF_THREAD, Thread, strandFlare } from '../engine/thread3d';
import { Bead, beadGeometry } from '../engine/bead';
import { LIN } from '../engine/palette';
import { LOOK, glow } from '../engine/look';
import { slam } from '../engine/motion';
import { cocPx } from '../engine/dof';
import { FPS, clamp, ease, frameIdx, keys, lerp, prog, pulse } from '../engine/util';
import { fitKey } from './diff-fx';
import { timesOf, type Times } from './graph-time';
import {
  BEAD_R, FOV, NODES, PEARL, STANDING, THREAD_R, bloodAt, dangleAt, hang, looseEnd, mossAt, runAt, seeded,
  type NodeId, type V3,
} from './graph-world';
import { ADV, Labels } from './graph-labels';
import { glowAlong, glowDot, glowRing, type P2 } from './graph-glow';
import S from './graph.strings.json';

// ------------------------------------------------------------------------------------------------ the copy

const [PATH, EDITOR, NEOVIM, TZ, IST, WORKS, ACME, MAYA, FORWARD, TRIP, HOTEL, CITY, VOCAB, ANSWER, K8S, KUBE] =
  S as string[] as [string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string];
const len = (s: string) => Array.from(s).length;

/** The file's last eight lines, 11–18 (spec §11.4): the editor's window on it. */
export const FILE_LINES = [EDITOR, '', NEOVIM, '', TZ, '', IST, WORKS];
const LINK_ROW = 7;
/** The link's characters in its line: from `[[` to past `]]`. */
export const LINK = { from: WORKS.indexOf('[['), to: WORKS.indexOf(']]') + 2 };
/** Where the trip's name sits in the forward link (code points). */
export const TAG_NAME = { from: len(FORWARD) - 2 - len(TRIP), to: len(FORWARD) - 2 };
/** The answer, as the terminal prints it (indented as output), and where `k8s` and the arrow sit in it. */
export const ANSWER_LINE = `  ${ANSWER}`;
export const ALIAS = { from: 2, to: 2 + len(K8S) };
const ARROW = ANSWER_LINE.indexOf('→');

// ------------------------------------------------------------------------------------------------ the world

/** The editor: diff's file at its size (640 px wide, 24 px code), its window the file's last 8 lines; m per 1000 px. */
const EDIT_SIZE = 24;
const EDIT_W = 640;
const EDIT_SCALE = 0.4;
/** Where it hangs (m) and its turn toward the constellation (radians about y). */
const EDIT_AT: V3 = [-0.47, 0.03, 0.02];
const EDIT_YAW = 0.36;
/**
 * The thread lies this far off the page (panel px, its centre) under the link; before it lifts it hums (TENSION: its
 * amplitude in px and frequency in Hz). Its free end curls up off the page past `]]` (OUT: how far along the line, up
 * and out of the page it reaches, m), and on the downbeat the whole underline zips along under the text and leaves the
 * page there, after its head: the link's thread lifting off it, never crossing its letters.
 */
const LIE = 6.5;
const TENSION = { px: 1.6, hz: 23 };
const OUT = { along: 0.03, up: 0.012, out: 0.042 };
/**
 * The studio turns as the scene plays (radians a second), and swings further on its hits, so the softboxes' reflections
 * sweep across the glass: the lift, the heal and the find (each `swing` radians, over `dur` s).
 */
const STUDIO = { drift: 0.22, swing: 0.55, dur: 0.45 };
/** The terminal: code size, width (panel px); its distance from the lens in the summary (m) and its centre in frame (px). */
const TERM_SIZE = 32;
const TERM_W = 1020;
export const TERM_AT = { dist: 0.6, x: 960, y: 826 };
/** The forward link's tag rides above its loose end, its right end there (m: across, up to its baseline). */
const TAG = { dx: 0.004, dy: 0.018 };
/** Label em (m), gap from its bead (bead radii), and how far it floats toward the lens from it (m). */
const LABEL_EM = 0.0102;
const LABEL_GAP = 1.5;
const LABEL_FLOAT = 0.024;
/** Glow levels (look.ts): the blood dashes, the moss of a heal and a walk, a pearl lit. */
const GLOW = { blood: 2.2, moss: 2.0, pearl: 3.2 };
/** Dangling thread samples. */
const N_DANGLE = 40;
/** Apertures: the close-up on the line, and the constellation. */
const FSTOP = { close: 3.2, wide: 3.4 };

const INK = new THREE.Color().setRGB(...LIN.ink);
const Y = new THREE.Vector3(0, 1, 0);
const WORLD = new THREE.Matrix4();
const v3 = (p: V3) => new THREE.Vector3(p[0], p[1], p[2]);
const P = (id: NodeId) => v3(NODES[id].pos);

interface Node {
  id: NodeId;
  bead: THREE.Mesh;
  pearl: THREE.Mesh;
  pearlMat: THREE.MeshPhysicalMaterial;
}

export default class Graph extends Scene {
  private T!: Times;
  private stage!: Stage;
  private rig!: CameraRig;
  /** After the cut: acme.md in close-up as the search lands. */
  private closeRig!: CameraRig;
  private scratch = new THREE.PerspectiveCamera(FOV, W / H, 0.01, 40);
  // the editor
  private edit!: Panel;
  private editG = new THREE.Group();
  private linkHalo!: Halo;
  // the terminal
  private term!: Panel;
  private termG = new THREE.Group();
  private termHome = new THREE.Vector3();
  private termQ = new THREE.Quaternion();
  private termScale = 1;
  private arrowHalo!: Halo;
  // the constellation
  private glass!: Bead;
  private beadGeo!: THREE.BufferGeometry;
  private pearlGeo!: THREE.SphereGeometry;
  private nodes = {} as Record<NodeId, Node>;
  private link!: Thread;
  private linkU = 0;
  private linkU1 = 0;
  private dangle!: Thread;
  private dangleVecs: THREE.Vector3[] = [];
  private tripHotel!: Thread;
  private hotelCity!: Thread;
  private standing: Thread[] = [];
  private search!: Thread;
  private searchU = 0;
  /** The search thread's head this frame (arc fraction). */
  private searchHead = 0;
  // type and light
  private labels!: Labels;
  private band!: THREE.Mesh;
  private bandMat!: THREE.ShaderMaterial;
  private blood = new Layer2D(960, 540, 1);
  private moss = new Layer2D(960, 540, 1);
  private mats: THREE.Material[] = [];
  /** The lens this frame (for the glow's blur). */
  private dof = { focus: 1, fstop: FSTOP.wide };

  override init() {
    const { renderer, vo, audio, start, end } = this.ctx;
    this.T = timesOf(vo, audio, start, end);
    this.stage = new Stage(renderer, { fov: FOV, near: 0.01, far: 30, envIntensity: 0.3 });
    this.buildEditor();
    this.buildNodes();
    this.buildThreads();
    this.buildLights();
    const k = this.keys();
    this.rig = new CameraRig(k.main);
    this.closeRig = new CameraRig(k.close);
    this.buildTerminal();
    this.buildSearch();
    this.labels = new Labels([ACME, MAYA, FORWARD, TRIP, HOTEL, CITY, KUBE, K8S].join(''), 160);
    this.stage.scene.add(this.labels.actors.mesh);
    this.buildBand();
    this.warmUp();
  }

  // ---------------------------------------------------------------------------------------------- the editor

  /** A point on the editor (px from its top left, y down; z px out of its face), in the world. */
  private edPt(x: number, y: number, z = 0) {
    this.editG.updateMatrixWorld(true);
    return new THREE.Vector3((x - EDIT_W / 2) / 1000, (this.edit.spec.h / 2 - y) / 1000, z / 1000).applyMatrix4(this.editG.matrixWorld);
  }

  private buildEditor() {
    this.edit = new Panel({ kind: 'editor', title: PATH, w: EDIT_W, rows: FILE_LINES.length, lang: 'md', gutter: 'numbers', firstLine: 11, size: EDIT_SIZE, lines: FILE_LINES.map((text) => ({ text })) });
    this.editG.add(this.edit.mesh);
    this.editG.scale.setScalar(EDIT_SCALE);
    this.editG.position.set(...EDIT_AT);
    this.editG.rotation.set(0, EDIT_YAW, 0);
    this.linkHalo = new Halo(this.edit.spec, 'moss', 60);
    this.editG.add(this.linkHalo.mesh);
    this.stage.scene.add(this.editG);
  }

  /** The link's cells: its left end and right end, and its baseline (editor px). */
  private linkCells() {
    const a = this.edit.cellOrigin(LINK_ROW, LINK.from), b = this.edit.cellOrigin(LINK_ROW, LINK.to);
    return { x0: a.x, x1: b.x, base: a.baseline };
  }

  /**
   * The link's centreline: along under the link's characters (lying on the page, lifted off it by `lift` 0..1), then
   * off the page and out into the dark to acme.md's pearl.
   */
  private linkPts(hum = 0) {
    const { x0, x1, base } = this.linkCells();
    const n = new THREE.Vector3(0, 0, 1).applyQuaternion(this.editG.quaternion);
    const r = new THREE.Vector3(1, 0, 0).applyQuaternion(this.editG.quaternion);
    const under = [0, 0.34, 0.67, 1].map((s) => this.edPt(lerp(x0 - 4, x1 + 2, s), base + 7, LIE + hum * Math.sin(Math.PI * s)));
    const L1 = under[3]!;
    // past `]]` it curls up off the page, and out into the dark to acme.md's pearl
    const pull = L1.clone().addScaledVector(r, OUT.along).addScaledVector(Y, OUT.up).addScaledVector(n, OUT.out);
    const A = P('acme');
    const mid = pull.clone().lerp(A, 0.5).addScaledVector(Y, 0.05).addScaledVector(n, 0.04);
    return [...under, pull, mid, A];
  }

  // ---------------------------------------------------------------------------------------------- the constellation

  private buildNodes() {
    const shape = { radius: BEAD_R, bore: THREAD_R * 1.5, chamfer: THREAD_R * 0.9 };
    this.beadGeo = beadGeometry(shape);
    this.glass = new Bead({ ...shape, text: '' }, { geometry: this.beadGeo });
    this.pearlGeo = new THREE.SphereGeometry(1, 40, 20);
    // the bore along the walk for the walk's beads (its thread runs through them), else turned anyhow
    const walk: Partial<Record<NodeId, [NodeId, NodeId]>> = { maya: ['c3', 'trip'], trip: ['maya', 'hotel'], hotel: ['trip', 'city'], city: ['hotel', 'c7'] };
    (Object.keys(NODES) as NodeId[]).forEach((id, i) => {
      const spec = NODES[id];
      const bead = new THREE.Mesh(this.beadGeo, this.glass.material);
      bead.scale.setScalar(spec.r / BEAD_R);
      bead.position.set(...spec.pos);
      const w = walk[id];
      const axis = w ? P(w[1]).sub(P(w[0])).normalize() : v3(seeded(i + 1)).normalize();
      const face = new THREE.Vector3(0, 0, 1).addScaledVector(axis, -axis.z);
      if (face.lengthSq() < 0.01) face.set(1, 0, 0).addScaledVector(axis, -axis.x);
      face.normalize();
      bead.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(axis, new THREE.Vector3().crossVectors(face, axis), face));
      const pearlMat = new THREE.MeshPhysicalMaterial({
        color: new THREE.Color().setRGB(...LIN.bone).multiplyScalar(0.86), roughness: 0.3, metalness: 0,
        sheen: 0.8, sheenRoughness: 0.35, sheenColor: new THREE.Color().setRGB(...LIN.boneDim), clearcoat: 0.7, clearcoatRoughness: 0.1,
      });
      const pearl = new THREE.Mesh(this.pearlGeo, pearlMat);
      pearl.scale.setScalar(spec.r * PEARL);
      pearl.position.set(...spec.pos);
      this.stage.scene.add(bead, pearl);
      this.mats.push(pearlMat);
      this.nodes[id] = { id, bead, pearl, pearlMat };
    });
  }

  private thread(points: THREE.Vector3[], o: { fuzz?: number; seed?: number; scale?: number } = {}) {
    const th = new Thread(points, { ...DIFF_THREAD, radius: THREAD_R * (o.scale ?? 1), fuzz: o.fuzz ?? 0, radialSegments: 12, seed: o.seed });
    th.setStrandLight({}, DIFF_THREAD.glow);
    this.stage.scene.add(th.mesh);
    return th;
  }

  private buildThreads() {
    // the link: along the underline, then off the page and out to acme.md's pearl
    const pts = this.linkPts();
    this.link = this.thread(pts, { fuzz: 0.6, seed: 0x11c });
    this.linkU = this.uNear(this.link, pts[3]!);
    this.linkU1 = this.uNear(this.link, pts[4]!);
    // the dangling link, maya.md to where the trip will be
    this.dangleVecs = Array.from({ length: N_DANGLE }, () => new THREE.Vector3());
    this.dangle = this.thread(this.danglePts(this.T.heal + 0.4), { fuzz: 0.4, seed: 0xd4 });
    // the trip's own link, to its hotel (drawn on as it is written)
    this.tripHotel = this.thread(hang(NODES.trip.pos, NODES.hotel.pos, 0.012, 9).map(v3), { seed: 0x7a });
    // the graph that is there throughout
    STANDING.forEach(([a, b, sag, k], i) => {
      const th = this.thread(hang(NODES[a].pos, NODES[b].pos, sag, 9).map(v3), { seed: 0x300 + i, scale: k });
      this.standing.push(th);
      if (a === 'hotel' && b === 'city') this.hotelCity = th;
    });
  }

  /** The dangling thread's points at t (into the scratch vectors). */
  private danglePts(t: number) {
    const pts = dangleAt(t, NODES.maya.pos, NODES.trip.pos, this.T.heal, N_DANGLE);
    return pts.map((p, i) => this.dangleVecs[i]!.set(p[0], p[1], p[2]));
  }

  /** The arc fraction of a thread nearest a point. */
  private uNear(th: Thread, p: THREE.Vector3) {
    let best = 0, bd = Infinity;
    for (let i = 0; i <= 2000; i++) {
      const d = th.pointAt(i / 2000).distanceToSquared(p);
      if (d < bd) (bd = d), (best = i / 2000);
    }
    return best;
  }

  // ---------------------------------------------------------------------------------------------- the terminal

  private buildTerminal() {
    const T = this.T;
    const cmd: PanelLine = { text: VOCAB, kind: 'cmd', at: T.type.at, cps: (len(VOCAB) - 3) / (T.type.end - T.type.at) };
    const out: PanelLine = { text: ANSWER_LINE, kind: 'out', at: T.answer, spans: [{ from: ARROW, to: ARROW + 1, tone: 'moss' }] };
    const g = panelLayout({ kind: 'terminal', size: TERM_SIZE, lines: [cmd, out] });
    const h = g.bar + g.padTop + 2 * g.lineH + g.padBottom;
    this.term = new Panel({ kind: 'terminal', w: TERM_W, h, size: TERM_SIZE, lines: [cmd, out] });
    this.termG.add(this.term.mesh);
    this.arrowHalo = new Halo(this.term.spec, 'moss', 30);
    this.termG.add(this.arrowHalo.mesh);
    this.stage.scene.add(this.termG);
    // where it stands: in the foreground of the summary, square to the lens, TERM_AT.dist off it, low in the frame, one
    // panel px to a frame px
    const cam = this.camAt(T.answer);
    const px = (TERM_AT.dist * 2 * Math.tan(THREE.MathUtils.degToRad(FOV) / 2)) / H;
    const right = new THREE.Vector3(1, 0, 0).applyQuaternion(cam.quaternion), up = new THREE.Vector3(0, 1, 0).applyQuaternion(cam.quaternion);
    const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(cam.quaternion);
    this.termScale = px * 1000;
    this.termHome.copy(cam.position).addScaledVector(fwd, TERM_AT.dist).addScaledVector(right, (TERM_AT.x - W / 2) * px).addScaledVector(up, (H / 2 - TERM_AT.y) * px);
    this.termQ.copy(cam.quaternion);
    this.termG.scale.setScalar(this.termScale);
    this.termG.position.copy(this.termHome);
    this.termG.quaternion.copy(this.termQ);
  }

  /** A point on the terminal (px from its top left, y down; z px out of its face), in the world, where it stands. */
  private termPt(x: number, y: number, z = 0) {
    const m = new THREE.Matrix4().compose(this.termHome, this.termQ, new THREE.Vector3().setScalar(this.termScale));
    return new THREE.Vector3((x - TERM_W / 2) / 1000, (this.term.spec.h / 2 - y) / 1000, z / 1000).applyMatrix4(m);
  }

  private buildSearch() {
    // `k8s` lifts off the answer: along under it, off the panel toward the lens, and up into the graph to acme.md
    const a = this.term.cellOrigin(1, ALIAS.from), b = this.term.cellOrigin(1, ALIAS.to);
    const y = a.baseline + 8;
    const lie = (0.75 * THREAD_R * 1000) / this.termScale + 2;
    const under = [0, 0.5, 1].map((s) => this.termPt(lerp(a.x - 3, b.x + 2, s), y, lie));
    const K1 = under[2]!, A = P('acme');
    const n = new THREE.Vector3(0, 0, 1).applyQuaternion(this.termQ);
    const off = K1.clone().addScaledVector(n, -0.03).addScaledVector(Y, 0.035);
    const below = A.clone().add(new THREE.Vector3(0.012, -0.16, 0.03)), near = A.clone().add(new THREE.Vector3(0.002, -0.06, 0.006));
    this.search = this.thread([...under, off, below, near, A], { seed: 0x5ea, scale: 0.75 });
    this.searchU = this.uNear(this.search, K1);
  }

  // ---------------------------------------------------------------------------------------------- the highlight

  /** The band of moss light under the word the search finds: a highlighter, swept on from its left. */
  private buildBand() {
    this.bandMat = new THREE.ShaderMaterial({
      uniforms: { uColor: { value: new THREE.Vector3(...glow('moss', 1)) }, uLevel: { value: 0 }, uFill: { value: 0 }, uSize: { value: new THREE.Vector2(1, 1) } },
      vertexShader: /* glsl */ `varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
      fragmentShader: /* glsl */ `uniform vec3 uColor; uniform float uLevel, uFill; uniform vec2 uSize; varying vec2 vUv;
        void main() {
          vec2 p = vUv * uSize; vec2 q = min(p, uSize - p);
          float r = 0.18 * uSize.y; vec2 c = max(vec2(r) - q, 0.0); float d = length(c) - r;
          float k = clamp(0.5 - d / max(fwidth(d), 1e-5), 0.0, 1.0);
          float fill = smoothstep(uFill * uSize.x - 0.04 * uSize.x, uFill * uSize.x, p.x);
          float edge = exp(-pow((p.x - uFill * uSize.x) / (0.03 * uSize.x), 2.0)) * step(uFill, 0.999);
          gl_FragColor = vec4(uColor * uLevel * k * ((1.0 - fill) + 3.0 * edge), 1.0);
        }`,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    });
    this.band = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), this.bandMat);
    this.band.renderOrder = 2;
    this.band.frustumCulled = false;
    this.stage.scene.add(this.band);
  }

  // ---------------------------------------------------------------------------------------------- lights

  private buildLights() {
    const s = this.stage.scene, c = new THREE.Vector3(0.25, 0.02, -0.2);
    // neutral light only (lit bone stays out of the bloom's chroma gate): a key from the upper left with a softbox over
    // it, a hard rim from behind and above that draws the threads and the glass out of the dark, a second rim from the
    // other side, a broad soft panel far behind the constellation that rings every bead's edge, and a low glow among
    // the beads that wakes their pearls
    initAreaLights();
    const box = new THREE.RectAreaLight(0xffffff, 0.6, 1.6, 0.6);
    box.position.copy(c).add(new THREE.Vector3(-0.7, 0.9, 1.0));
    box.lookAt(c);
    const key = new THREE.DirectionalLight(0xffffff, 0.75);
    key.position.copy(c).add(new THREE.Vector3(-1.3, 1.6, 1.4));
    key.target.position.copy(c);
    const rim = new THREE.DirectionalLight(0xffffff, 4.2);
    rim.position.copy(c).add(new THREE.Vector3(0.9, 1.2, -1.8));
    rim.target.position.copy(c);
    const rim2 = new THREE.DirectionalLight(0xffffff, 2.0);
    rim2.position.copy(c).add(new THREE.Vector3(-1.5, 0.4, -1.4));
    rim2.target.position.copy(c);
    const back = new THREE.RectAreaLight(0xffffff, 2.2, 3.2, 1.2);
    back.position.copy(c).add(new THREE.Vector3(0.2, 0.5, -2.2));
    back.lookAt(c.clone().add(new THREE.Vector3(0, 0, 1)));
    const glowL = new THREE.PointLight(0xffffff, 0.35, 0, 2);
    glowL.position.copy(c).add(new THREE.Vector3(-0.1, 0.25, 0.45));
    s.add(box, key, key.target, rim, rim.target, rim2, rim2.target, back, glowL);
  }

  // ---------------------------------------------------------------------------------------------- the camera

  /** World points boxing editor px [x0, x1] × [y0, y1]. */
  private edBox(x0: number, y0: number, x1: number, y1: number) {
    return [this.edPt(x0, y0), this.edPt(x1, y0), this.edPt(x0, y1), this.edPt(x1, y1)];
  }

  private keys(): { main: CamKey[]; close: CamKey[] } {
    const T = this.T, E = this.editG.matrixWorld, g = this.edit.layout;
    this.editG.updateMatrixWorld(true);
    const r6 = this.edit.rowTop(6), r7 = this.edit.rowTop(7), rb = r7 + g.lineH;
    const xEnd = this.edit.cellOrigin(LINK_ROW, len(WORKS)).x;
    const { x0, x1 } = this.linkCells();
    const L1 = this.edPt(x1, rb), A = P('acme'), M = P('maya'), Tp = P('trip'), Hh = P('hotel'), C = P('city');
    const end = v3(looseEnd(T.ping + 0.1, NODES.maya.pos, NODES.trip.pos, T.heal).end);
    const tag = end.clone().add(new THREE.Vector3(TAG.dx - len(FORWARD) * ADV * LABEL_EM, TAG.dy + LABEL_EM, 0));
    const mL = M.clone().add(new THREE.Vector3(-NODES.maya.r * 2.2, 0.01, 0)), ringTop = Tp.clone().add(new THREE.Vector3(0, NODES.trip.r * 1.8, 0));
    // the tag follows its end onto the trip as the link heals: its far end then
    const tagHome = P('trip').add(new THREE.Vector3(NODES.trip.r * LABEL_GAP + len(TRIP) * ADV * LABEL_EM, 0, 0));
    const label = (id: NodeId, n: number) => P(id).add(new THREE.Vector3(NODES[id].r * LABEL_GAP + n * ADV * LABEL_EM, 0, 0));
    const graph = [A, M, Tp, Hh, C, label('hotel', len(HOTEL)), label('city', len(CITY))];
    const summary = fitKey(T.answer, graph, { az: 8, el: 7, fov: FOV, margin: [0.075, 0.065], bias: [0.01, 0.44], roll: 0.4 }, WORLD, ease.inOutQuad);
    // as `k8s` lifts off, the camera tips up after the thread, toward the graph
    const up = (k: CamKey, t: number, dy: number, toward: THREE.Vector3, w: number): CamKey => {
      const target = v3(k.target).lerp(toward, w).add(new THREE.Vector3(0, dy, 0));
      return { t, pos: v3(k.pos).add(new THREE.Vector3(0, 0.6 * dy, 0)).toArray() as V3, target: target.toArray() as V3, fov: FOV, roll: 0.2, ease: ease.inCubic };
    };
    const acmeBox = [A, label('acme', len(KUBE) + 1), A.clone().add(new THREE.Vector3(0, -0.035, 0)), A.clone().add(new THREE.Vector3(-0.03, 0.03, 0))];
    const close = [
      fitKey(T.cut, acmeBox, { az: 9, el: 4, fov: FOV, margin: [0.3, 0.33], bias: [0.02, 0.0], roll: 0.9 }, WORLD),
      fitKey(T.end, acmeBox, { az: 6, el: 5, fov: FOV, margin: [0.36, 0.4], bias: [0.02, 0.02], roll: 1.1 }, WORLD, ease.outQuad),
    ];
    const main = [
      // the cut: in close on the line, from a little left of square, drifting in along it toward the link
      fitKey(T.start, this.edBox(g.padX - 6, r6 + 6, xEnd + 12, rb + 4), { az: -17, el: 7, fov: FOV, margin: [0.08, 0.3], bias: [0.02, -0.16], roll: -2.2 }, E),
      fitKey(T.lift - 0.03, this.edBox(x0 - 150, r7 - 6, x1 + 26, rb + 8), { az: -13, el: 6, fov: FOV, margin: [0.12, 0.36], bias: [0.06, -0.12], roll: -1.6 }, E, ease.inOutQuad),
      // the thread races off the page: the camera pulls back and round after it, and holds the edge as it lands
      fitKey(T.land + 0.12, [L1, A, A.clone().add(new THREE.Vector3(NODES.acme.r * LABEL_GAP + len(ACME) * ADV * LABEL_EM, 0, 0))], { az: 3, el: 5, fov: FOV, margin: [0.14, 0.3], bias: [0.02, -0.08], roll: -0.9 }, WORLD, ease.inOutCubic),
      // "the dots…": open on the constellation, the dangling link in the middle of the frame
      fitKey(T.ping + 0.1, [mL, end, tag, ringTop], { az: 3, el: 10, fov: FOV, margin: [0.1, 0.2], bias: [0, 0], roll: -3.2 }, WORLD, ease.inOutCubic),
      fitKey(T.heal - 0.03, [mL, end, tag, ringTop, tagHome], { az: 5, el: 9, fov: FOV, margin: [0.07, 0.15], bias: [0, 0], roll: -2.2 }, WORLD, ease.inOutQuad),
      // the walk: the camera pulls back with it, and on as the terminal rises into the foreground under the graph
      fitKey(T.hops[2]! + 0.12, graph, { az: 7, el: 7, fov: FOV, margin: [0.1, 0.09], bias: [0, 0.44], roll: 0.3 }, WORLD, ease.inOutCubic),
      summary,
      up(summary, T.cut, 0.05, A, 0.3),
    ];
    return { main, close };
  }

  /** Place a camera for t: the continuous shot, then acme.md in close-up from the cut. */
  private aim(cam: THREE.PerspectiveCamera, t: number) {
    (t < this.T.cut ? this.rig : this.closeRig).apply(cam, t);
  }

  /** A scratch camera where the rig has the stage's at t. */
  private camAt(t: number) {
    this.aim(this.scratch, t);
    return this.scratch;
  }

  // ---------------------------------------------------------------------------------------------- posing

  private poseLink(t: number) {
    const T = this.T, th = this.link;
    // under the link, drawn on in the beat before the downbeat; then off the page and out to acme.md, landing on the eighth
    // it hums as it tightens under the link; its free end curls up off the page past `]]`; on the downbeat the head whips
    // away out into the dark to acme.md, landing on the eighth, and the underline zips along under the text after it
    const tense = t > T.underline.end - 0.05 && t < T.lift - 0.1 ? TENSION.px * Math.sin(2 * Math.PI * TENSION.hz * t) * prog(t, T.underline.end - 0.05, T.lift - 0.13) : 0;
    th.setPoints(this.linkPts(tense));
    const under = prog(t, T.underline.at, T.underline.end, ease.outCubic);
    const curl = prog(t, T.lift - 0.14, T.lift, ease.inOutCubic);
    const fly = prog(t, T.lift, T.land, (x) => 1 - Math.pow(1 - x, 2.4));
    const head = t < T.lift ? lerp(this.linkU * under, this.linkU1, curl) : lerp(this.linkU1, 1, fly);
    const tail = this.linkU * prog(t, T.lift - 0.02, T.lift + 0.16, ease.inCubic);
    th.setDraw(tail, Math.max(tail + 1e-4, head));
    th.mesh.visible = head - tail > 0.002;
    // the moss of the edge landing runs back down it to the link, and leaves an ember
    th.setStrandGlow({ moss: DIFF_THREAD.rest, blood: DIFF_THREAD.rest });
    th.setStrandLight({ moss: Float64Array.from({ length: 128 }, (_, i) => runAt(t, 1 - i / 127, T.land, T.land + 0.32, 0.3)) });
    // the link's text takes the moss as it arrives
    const { x0, x1, base } = this.linkCells();
    const k = strandFlare(t, T.land + 0.3, { lead: 0.08, decay: 0.7 });
    this.linkHalo.set((x0 + x1) / 2, base - 9, 1.4 * k, 34);
    this.linkHalo.mesh.scale.set((x1 - x0 + 90) / 1000, 60 / 1000, 1);
    this.edit.draw(t);
  }

  private poseConstellation(t: number) {
    const T = this.T;
    // the dangling link: thrown out from maya.md as the camera opens out, falling short; dashes of blood running down it
    const thrown = prog(t, T.land + 0.05, T.ping - 0.04, ease.outCubic);
    const dg = this.dangle;
    dg.setPoints(this.danglePts(t));
    dg.setDraw(0, Math.max(1e-4, thrown));
    dg.mesh.visible = thrown > 0.002;
    const ping = pulse(t, T.ping, 0.18);
    const N = 160;
    const bloodEnv = new Float64Array(N), mossEnv = new Float64Array(N);
    for (let i = 0; i < N; i++) {
      const u = i / (N - 1);
      bloodEnv[i] = bloodAt(u, t, T.heal, T.hops[0]!) * (u <= thrown ? 1 : 0) * (0.75 + 0.25 * ping);
      mossEnv[i] = mossAt(u, t, T.heal, T.hops[0]!);
    }
    dg.setStrandGlow({ blood: DIFF_THREAD.rest, moss: DIFF_THREAD.rest });
    dg.setStrandLight({ blood: bloodEnv, moss: mossEnv });

    // the trip: written on the heal, dropping in where the link pointed
    const trip = this.nodes.trip;
    const s = slam(t, T.heal - 0.03, { freq: 5.5, damping: 0.55 });
    const on = s > 0.002;
    trip.bead.visible = trip.pearl.visible = on;
    if (on) {
      const p = P('trip').add(new THREE.Vector3(0, 0.05 * (1 - s), -0.08 * (1 - s)));
      trip.bead.position.copy(p);
      trip.bead.scale.setScalar(Math.max(1e-3, s) * (NODES.trip.r / BEAD_R));
      trip.pearl.position.copy(p);
      trip.pearl.scale.setScalar(Math.max(1e-3, s) * NODES.trip.r * PEARL);
    }
    // its own link to the hotel, drawn on as it is written
    const th2 = prog(t, T.heal, T.hops[0]! + 0.02, ease.outCubic);
    this.tripHotel.setDraw(0, Math.max(1e-4, th2));
    this.tripHotel.mesh.visible = th2 > 0.002;
    // the walk: moss running on, trip to hotel, hotel to city
    const hop = (t0: number, t1: number) => Float64Array.from({ length: 96 }, (_, i) => runAt(t, i / 95, t0, t1, 0.4));
    this.tripHotel.setStrandGlow({ moss: DIFF_THREAD.rest, blood: DIFF_THREAD.rest });
    this.tripHotel.setStrandLight({ moss: hop(T.hops[0]!, T.hops[1]!) });
    this.hotelCity.setStrandGlow({ moss: DIFF_THREAD.rest, blood: DIFF_THREAD.rest });
    this.hotelCity.setStrandLight({ moss: hop(T.hops[1]!, T.hops[2]!) });

    // pearls: lit moss as the walk reaches them (and acme.md as the edge lands, and as the search finds it)
    const lit = this.pearlLight(t);
    for (const id of Object.keys(this.nodes) as NodeId[]) {
      const k = lit[id] ?? 0;
      const e = this.nodes[id].pearlMat.emissive;
      if (k > 0.001) e.setRGB(...glow('moss', GLOW.pearl * k));
      else e.setRGB(0, 0, 0);
    }
  }

  /** How lit each pearl is at t (0..1): acme.md as the edge lands and as the search finds it, the walk's as it reaches them. */
  private pearlLight(t: number): Partial<Record<NodeId, number>> {
    const T = this.T;
    const reached = (at: number, ember = 0.3) => (t >= at - 0.03 ? Math.max(ember, strandFlare(t, at, { lead: 0.03, decay: 0.8 })) : 0);
    return {
      acme: Math.max(strandFlare(t, T.land, { lead: 0.03, decay: 0.9 }), t >= T.found - 0.03 ? Math.max(0.45, strandFlare(t, T.found, { lead: 0.03, decay: 1.2 })) : 0),
      maya: reached(T.heal, 0.25),
      trip: reached(T.hops[0]!),
      hotel: reached(T.hops[1]!),
      city: reached(T.hops[2]!),
    };
  }

  private poseTerminal(t: number) {
    const T = this.T;
    // it rises into the foreground as the walk lands, tipping up to face the lens
    const s = slam(t, T.rise + 0.22, { freq: 3.6, damping: 0.72 });
    this.termG.visible = s > 0.001;
    if (!this.termG.visible) return;
    const up = new THREE.Vector3(0, 1, 0).applyQuaternion(this.termQ);
    this.termG.position.copy(this.termHome).addScaledVector(up, -0.2 * (1 - s));
    this.termG.quaternion.copy(this.termQ).multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), -0.9 * (1 - s)));
    this.term.opacity = clamp(s * 1.6);
    // `k8s` is selected as the search takes it (on the frame grid: one state per shutter)
    const tq = frameIdx(t) / FPS;
    const sel = prog(tq, T.seek - 0.12, T.seek, ease.outCubic) * (1 - prog(tq, T.found + 0.1, T.found + 0.5));
    this.term.select(sel > 0.02 ? 1 : null, ALIAS.from, ALIAS.to, 0.16 * sel);
    this.term.draw(t);
    // the answer: the arrow's moss flares as it lands, and keeps a glow
    const a = this.term.cellOrigin(1, ARROW);
    const flare = strandFlare(t, T.answer + 0.04, { lead: 0.02, decay: 0.6 });
    this.arrowHalo.set(a.x + 0.5 * this.term.adv, a.baseline - 0.3 * TERM_SIZE, 0.45 * flare, 16);
  }

  private poseSearch(t: number) {
    const T = this.T, th = this.search;
    const under = prog(t, T.seek - 0.14, T.seek, ease.outCubic);
    const fly = prog(t, T.seek, T.found, (x) => 1 - Math.pow(1 - x, 2.4));
    const head = t < T.seek ? this.searchU * under : lerp(this.searchU, 1, fly);
    this.searchHead = head;
    th.setDraw(0, Math.max(1e-4, head));
    th.mesh.visible = head > 0.002;
    th.setStrandGlow({ moss: DIFF_THREAD.rest, blood: DIFF_THREAD.rest });
    th.setStrandLight({ moss: Float64Array.from({ length: 128 }, (_, i) => runAt(t, 1 - i / 127, T.found, T.found + 0.3, 0.3)) });
  }

  // ---------------------------------------------------------------------------------------------- labels

  private poseLabels(t: number) {
    const T = this.T, L = this.labels, cam = this.stage.camera;
    L.begin(cam);
    const { right, up, back } = L.basis;
    const bone = LIN.bone, dim = LIN.boneDim, moss = LIN.moss;
    // a label floats a little toward the lens from its bead, so neither the glass nor a thread ever cuts through it
    const place = (id: NodeId) => P(id).addScaledVector(right, NODES[id].r * LABEL_GAP).addScaledVector(up, -0.36 * LABEL_EM).addScaledVector(back, LABEL_FLOAT);
    const mixc = (a: readonly number[], b: readonly number[], k: number) => [lerp(a[0]!, b[0]!, k), lerp(a[1]!, b[1]!, k), lerp(a[2]!, b[2]!, k)] as [number, number, number];
    // acme.md: its name comes up as the edge lands
    const acmeIn = prog(t, T.land - 0.02, T.land + 0.12, ease.outCubic);
    const found = prog(t, T.found - 0.02, T.found + 0.15, ease.outCubic);
    L.text(ACME, place('acme'), { em: LABEL_EM, color: mixc(dim, bone, Math.max(strandFlare(t, T.land, { decay: 0.8 }), found)), alpha: acmeIn });
    // the others are there as the constellation opens; the walk lights the trip, the hotel and the city moss
    const open = prog(t, T.land, T.land + 0.3);
    L.text(MAYA, place('maya'), { em: LABEL_EM, color: dim, alpha: open });
    const visited = (h: number) => prog(t, T.hops[h]! - 0.02, T.hops[h]! + 0.08);
    L.text(HOTEL, place('hotel'), { em: LABEL_EM, color: mixc(dim, moss, visited(1)), alpha: open });
    L.text(CITY, place('city'), { em: LABEL_EM, color: mixc(dim, moss, visited(2)), alpha: open });

    // the forward link's tag at the loose end, typed on as the thread falls short; it rides up with the end into the trip's
    // bead, and when the moss reaches the trip it resolves: its path and brackets fall away and the name slides home
    const thrown = prog(t, T.land + 0.05, T.ping - 0.04, ease.outCubic);
    // (typed on the output frame grid: one state per shutter, so a character never lands mid-frame)
    const tq = frameIdx(t) / FPS;
    const typed = Math.floor(clamp((tq - (T.ping - 0.1)) * 260, 0, len(FORWARD)));
    if (typed > 0) {
      const { end } = looseEnd(t, NODES.maya.pos, NODES.trip.pos, T.heal);
      const tagAt = v3(end).addScaledVector(right, TAG.dx - len(FORWARD) * ADV * LABEL_EM).addScaledVector(up, TAG.dy).addScaledVector(back, LABEL_FLOAT);
      const home = place('trip');
      const k = prog(t, T.hops[0]! - 0.03, T.hops[0]! + 0.16, ease.inOutCubic);
      const gone = prog(t, T.hops[0]! - 0.04, T.hops[0]! + 0.08, ease.inQuad);
      const col = mixc(mixc(LIN.bloodBright, dim, k), moss, visited(0));
      L.text(FORWARD, tagAt, {
        em: LABEL_EM, color: col, alpha: thrown, n: typed,
        each: (i) => {
          if (i < TAG_NAME.from || i >= TAG_NAME.to) return { alpha: 1 - gone, off: [0, -0.02 * gone, 0] };
          // the name glides from its place in the tag to its place by the bead
          const from = tagAt.clone().addScaledVector(right, i * ADV * LABEL_EM);
          const to = home.clone().addScaledVector(right, (i - TAG_NAME.from) * ADV * LABEL_EM);
          const d = to.sub(from).multiplyScalar(k);
          return { off: [d.dot(right), d.dot(up), 0] };
        },
      });
    }

    // the query rides the search out: `k8s` beside the thread a little behind its head, and stays by it when it lands
    if (t > T.seek) {
      const u = Math.max(this.searchU + 0.02, this.searchHead - 0.034);
      const at = this.search.pointAt(u).addScaledVector(right, 0.009).addScaledVector(up, -0.004);
      const k = prog(t, T.seek, T.seek + 0.08);
      L.text(K8S, at, { em: LABEL_EM, color: mixc(dim, bone, prog(t, T.found - 0.05, T.found + 0.1)), alpha: k });
    }

    // the word the search finds, under acme.md's name, in moss light
    const word = prog(t, T.found, T.found + 0.1);
    const wAt = place('acme').addScaledVector(up, -1.6 * LABEL_EM);
    L.text(KUBE, wAt, { em: LABEL_EM, color: bone, alpha: word, n: Math.floor(clamp((tq - T.found) * 160 + 1, 0, len(KUBE))) });
    L.end();
    // the highlighter under it
    const fill = prog(t, T.found - 0.01, T.found + 0.16, ease.outCubic);
    this.band.visible = fill > 0.001;
    if (this.band.visible) {
      const w = len(KUBE) * ADV * LABEL_EM + 0.36 * LABEL_EM, h = 0.62 * LABEL_EM;
      this.band.quaternion.copy(cam.quaternion);
      this.band.scale.set(w, h, 1);
      this.band.position.copy(wAt).addScaledVector(right, w / 2 - 0.18 * LABEL_EM).addScaledVector(up, 0.14 * LABEL_EM);
      (this.bandMat.uniforms.uSize!.value as THREE.Vector2).set(w * 1000, h * 1000);
      this.bandMat.uniforms.uFill!.value = fill;
      this.bandMat.uniforms.uLevel!.value = 0.34;
    }
  }

  // ---------------------------------------------------------------------------------------------- glow on screen

  private toScreen(p: THREE.Vector3): P2 {
    const q = p.clone().project(this.stage.camera);
    return { x: ((q.x + 1) / 2) * W, y: ((1 - q.y) / 2) * H };
  }

  /** A thread's centreline on screen, and the lens's blur along it (px). */
  private onScreen(th: Thread, n = 48): { pts: P2[]; blur: (u: number) => number } {
    const pts: P2[] = [], coc: number[] = [];
    for (let i = 0; i <= n; i++) {
      const p = th.pointAt(i / n);
      pts.push(this.toScreen(p));
      coc.push(cocPx(Math.max(0.02, this.stage.depthOf(p)), this.dof, FOV, H));
    }
    return { pts, blur: (u) => coc[Math.min(n, Math.round(u * n))]! };
  }

  /** The light the threads carry, on screen: blood dashes, moss heal, walk, landings; pearls lit. */
  private drawGlow(t: number) {
    const T = this.T, B = this.blood.ctx, M = this.moss.ctx;
    this.blood.clear();
    this.moss.clear();
    B.scale(0.5, 0.5);
    M.scale(0.5, 0.5);
    const any = { b: false, m: false };
    const along = (c: CanvasRenderingContext2D, th: Thread, n: number, level: (u: number) => number, gain = 1) => {
      const s = this.onScreen(th, n);
      glowAlong(c, s.pts, level, gain, undefined, s.blur);
    };
    // the dangling link
    const thrown = prog(t, T.land + 0.05, T.ping - 0.04, ease.outCubic);
    if (thrown > 0.002) {
      const ping = pulse(t, T.ping, 0.18);
      along(B, this.dangle, 80, (u) => bloodAt(u, t, T.heal, T.hops[0]!) * (u <= thrown ? 1 : 0) * (0.8 + 0.6 * ping));
      any.b = true;
      // where the link points: the place the trip would be, an empty ring of blood light until it is written
      const ring = prog(t, T.land + 0.25, T.ping - 0.05) * (1 - prog(t, T.heal - 0.06, T.heal));
      if (ring > 0.004) {
        const q = this.toScreen(P('trip')), r = this.pxPerM(P('trip')) * NODES.trip.r;
        glowRing(B, q.x, q.y, r, 0.55 * ring * (0.8 + 0.5 * pulse(t, T.ping, 0.15)), 0.12 * t);
      }
      // the loose end pings on the beat, unanswered
      const k = pulse(t, T.ping, 0.12) * (t < T.heal ? 1 : 0);
      if (k > 0.004) {
        const end = v3(looseEnd(t, NODES.maya.pos, NODES.trip.pos, T.heal).end), q = this.toScreen(end);
        glowDot(B, q.x, q.y, 26, 0.8 * k);
      }
      if (t > T.heal) {
        along(M, this.dangle, 80, (u) => mossAt(u, t, T.heal, T.hops[0]!));
        any.m = true;
      }
    }
    // the edge landing in acme.md, its moss running back to the link
    if (t > T.land - 0.02 && t < T.land + 1.6) {
      along(M, this.link, 64, (u) => runAt(t, 1 - u, T.land, T.land + 0.32, 0.3), 0.8);
      any.m = true;
    }
    // the walk
    if (t > T.hops[0]! - 0.05) {
      along(M, this.tripHotel, 40, (u) => runAt(t, u, T.hops[0]!, T.hops[1]!, 0.4));
      along(M, this.hotelCity, 40, (u) => runAt(t, u, T.hops[1]!, T.hops[2]!, 0.4));
      any.m = true;
    }
    // the search landing
    if (t > T.found - 0.02) {
      along(M, this.search, 64, (u) => runAt(t, 1 - u, T.found, T.found + 0.3, 0.3), 0.8);
      any.m = true;
    }
    // pearls lit: a soft halo through the glass
    const lit = this.pearlLight(t);
    for (const id of Object.keys(lit) as NodeId[]) {
      const k = lit[id] ?? 0;
      if (k <= 0.004 || !this.nodes[id].pearl.visible) continue;
      const p = this.nodes[id].pearl.position, q = this.toScreen(p);
      const r = this.pxPerM(p) * NODES[id].r * 1.15 + 0.5 * cocPx(Math.max(0.02, this.stage.depthOf(p)), this.dof, FOV, H);
      glowDot(M, q.x, q.y, r, 0.45 * k);
      any.m = true;
    }
    return any;
  }

  /** Logical px per metre at a point's depth. */
  private pxPerM(p: THREE.Vector3) {
    const cam = this.stage.camera, d = -p.clone().applyMatrix4(cam.matrixWorldInverse).z;
    return H / (2 * Math.max(1e-3, d) * Math.tan(THREE.MathUtils.degToRad(cam.fov) / 2));
  }

  // ---------------------------------------------------------------------------------------------- render

  /** Focus (diopters, keyed): the link, the edge landing, the dangling link, the heal, the walk, the terminal, acme.md. */
  private focus(t: number) {
    const T = this.T, st = this.stage;
    const inv = (p: THREE.Vector3) => 1 / Math.max(0.03, st.depthOf(p));
    const { x0, x1, base } = this.linkCells();
    const link = this.edPt((x0 + x1) / 2, base - 8);
    const head = this.termPt(this.term.cellOrigin(0, 2 + (len(VOCAB) - 2) * clamp((t - T.type.at) / (T.type.end - T.type.at))).x, this.term.rowTop(0) + 20);
    const end = v3(looseEnd(t, NODES.maya.pos, NODES.trip.pos, T.heal).end);
    const ks: [number, number, ((x: number) => number)?][] = [
      [T.start, inv(link)],
      [T.lift, inv(link)],
      [T.land, inv(P('acme')), ease.inOutQuad],
      [T.ping, inv(P('maya').lerp(end, 0.75)), ease.inOutCubic],
      [T.heal, inv(P('trip')), ease.inOutQuad],
      [T.hops[2]!, inv(P('trip').lerp(P('hotel'), 0.5)), ease.inOutQuad],
      [T.rise + 0.22, inv(head), ease.inOutCubic],
      [T.answer, inv(head)],
    ];
    // after the cut, acme.md and its name
    if (t >= T.cut) {
      const A = P('acme'), toLens = st.camera.position.clone().sub(A).normalize();
      return { focus: st.depthOf(A.addScaledVector(toLens, 0.85 * LABEL_FLOAT)), fstop: FSTOP.wide };
    }
    return { focus: 1 / keys(t, ks), fstop: t < T.lift + 0.1 ? FSTOP.close : FSTOP.wide };
  }

  private warmUp() {
    const st = this.stage, rt = makeRT(W, H), T = this.T;
    const culled: THREE.Object3D[] = [];
    st.scene.traverse((o) => {
      if (o.frustumCulled) (o.frustumCulled = false), culled.push(o);
    });
    this.pose(T.found + 0.2);
    for (const n of Object.values(this.nodes)) n.bead.visible = n.pearl.visible = true;
    st.compile();
    st.render(rt, { dof: { focus: 1, fstop: 4 } });
    for (const o of culled) o.frustumCulled = true;
    rt.dispose();
  }

  private pose(t: number) {
    this.aim(this.stage.camera, t);
    const T = this.T, sw = (at: number) => STUDIO.swing * prog(t, at - 0.05, at - 0.05 + STUDIO.dur, ease.inOutCubic);
    this.stage.scene.environmentRotation.set(0, STUDIO.drift * (t - T.start) + sw(T.lift) + sw(T.heal) + sw(T.found), 0);
    this.dof = this.focus(t);
    this.poseLink(t);
    this.poseConstellation(t);
    this.poseTerminal(t);
    this.poseSearch(t);
    this.poseLabels(t);
  }

  render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides {
    const t = f.t, T = this.T, st = this.stage, { renderer, comp } = this.ctx;
    this.pose(t);
    const cc = renderer.getClearColor(new THREE.Color()), ca = renderer.getClearAlpha();
    renderer.setClearColor(INK, 1); // what the glass sees through the transmission pass
    st.render(out, { dof: this.dof });
    renderer.setClearColor(cc, ca);

    const any = this.drawGlow(t);
    if (any.b) comp.draw(renderer, this.blood.upload(), out, { mode: 'add', tint: glow('blood', GLOW.blood) });
    if (any.m) comp.draw(renderer, this.moss.upload(), out, { mode: 'add', tint: glow('moss', GLOW.moss) });

    // hits: the lift on the downbeat, the landing, the heal, the answer on its downbeat, the find
    const zoom = 0.006 * pulse(t, T.lift, 0.1) + 0.004 * pulse(t, T.land, 0.1) + 0.006 * pulse(t, T.heal, 0.12) + 0.005 * pulse(t, T.answer, 0.12) + 0.004 * pulse(t, T.found, 0.12);
    const dh = t - T.heal;
    const shake = dh >= 0 ? 2.2 * Math.exp(-dh * 20) * Math.cos(dh * 2 * Math.PI * 9) : 0;
    return { zoom: 1 + zoom, shake: [0, shake], vignette: LOOK.vignette + 0.04 };
  }

  override dispose() {
    const r = this.ctx.renderer;
    if (this.glass) freeTransmission(r, this.glass.material);
    this.edit?.dispose();
    this.term?.dispose();
    for (const x of [this.linkHalo, this.arrowHalo]) x?.dispose();
    for (const th of [this.link, this.dangle, this.tripHotel, this.search, ...this.standing]) th?.dispose();
    this.glass?.dispose();
    this.beadGeo?.dispose();
    this.pearlGeo?.dispose();
    this.labels?.dispose();
    this.band?.geometry.dispose();
    this.bandMat?.dispose();
    for (const m of this.mats) m.dispose();
    disposeLayer(this.blood);
    disposeLayer(this.moss);
    this.stage?.dispose();
  }
}
