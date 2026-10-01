// Scene 14 `anywhere`: "On your machine... or in my cloud." / "One memory for every user you have." (Plan 2 Task 24;
// spec §4 14, §11.7, §11.9.) She runs wherever you want her: a single binary on your machine, or her own cloud, and
// in her cloud every user you have gets a memory of their own. The last word before the woven mark.
//
// One world, two shots, every time from the data (her measured onsets, the score's beats; anywhere-time.ts):
// 1. The machine. Cut in on the downbeat: a terminal in close 3D on the left page of an open book in the dark, its
//    prompt breathing blood light, waiting. On "On" (its beat) the install line, `curl -fsSL https://gitloom.cloud/
//    install.sh | sh   # current: 0.3.0`, types in with her, the focus on it as the camera drifts along; over it her
//    headline "On your machine…" types in word by word and "machine" slams in from depth on her onset, extruded satin
//    bone. Enter, and the four chips are dealt out from under the terminal on sixteenths into the pause, `one static
//    binary` `no CGo` `arm64 + amd64` `licence verified offline`, the last with a ✔ drawn on in moss (verified); a light
//    glints across them.
// 2. The split, on the downbeat between "or" and "in": the camera whips back and right onto both pages, a hairline
//    drawing down the spine between them. The right page is her cloud, the console recreated (anywhere-console.ts): the
//    Playground, the Memory Graph and Namespaces deal in on sixteenths, and "…or in my cloud." comes up over them,
//    "cloud" slamming in on her onset. In the Playground the user's turn says "Maya moved to Lisbon in March 2026.";
//    on the beat on "cloud." the agent's `gitloom_retrieve` row opens, lit moss, and on the next `gitloom_remember`, lit
//    blood (it checks what it knows, then remembers), the reply's blood caret waiting under them. The Memory Graph
//    settles into its tier regions (anywhere-graph.ts: the console's own simulation, seeded, its time speed-ramped so the
//    burst reads), its green relations drawing on and flaring as they connect. The camera drifts in toward the cloud,
//    the focus racking from card to card; on "One" the first namespace, user-0001, opens in Namespaces.
// 3. The namespaces, on the downbeat on "for": a cut (half a frame before it) to user-0001 alone, a tile of its own,
//    and on each sixteenth after it the namespaces double (anywhere-field.ts), each copy sliding out from under its block
//    and landing with a moss flash, 1, 2, 4… 2,048 as she says "for every user you have.", the camera pulling back at a
//    constant rate on the doubling (√2 a doubling) and turning a little until the whole field of 64 by 32 recedes in the
//    dark, the far side soft. The label types in on "user", "one per end user · a storage boundary, not a WHERE clause",
//    the footnote on "have.", "free plan · no card · storage is free", and a light runs across the field as it lands.
import * as THREE from 'three';
import { Scene, type Frame, type PostOverrides } from '../engine/scene';
import { CameraRig, Stage, initAreaLights, type CamKey, type V3 } from '../engine/stage';
import { Layer2D, W, H, makeRT } from '../engine/gl';
import { Panel, panelLayout, type PanelLine } from '../engine/panels';
import { Halo, Wash } from '../engine/panel-light';
import { GlyphActors, GlyphAtlas } from '../engine/glyphs';
import { Mat, Type3D } from '../engine/type3d';
import { F, font } from '../engine/type';
import { LIN, rgba } from '../engine/palette';
import { glow } from '../engine/look';
import { slam } from '../engine/motion';
import { sweepAt, withSweep, type SweepBand } from '../engine/sweep';
import { FPS, clamp, ease, frameIdx, keys, lerp, prog, pulse, smootherstep } from '../engine/util';
import { Backdrop } from './diff-fx';
import { ChipShadow, chipGeometry } from './repo-chips';
import { DOUBLINGS, timesOf, type Times } from './anywhere-time';
import { CHIP, Check, Headline, chipNames, dealAt, layoutChipRows, penAt, type ChipPlace } from './anywhere-machine';
import {
  Card, GRAPH, NS, PLAY, opening, paintGraph, paintNamespaces, paintPlayground, playKey, toolBox, type ConsoleCopy, type PlayState,
} from './anywhere-console';
import { GraphView, TIERS, memoryGraph, simulate, type Sim } from './anywhere-graph';
import { Field, PITCH, TILE } from './anywhere-field';
import S from './anywhere.strings.json';

// ------------------------------------------------------------------------------------------------ the copy

const [HEAD_L, HEAD_R, INSTALL, CHIP_LINE, PLAYGROUND, MEMORY_GRAPH, NAMESPACES_T, MESSAGE, RETRIEVE, REMEMBER, ...REST] = S as string[] as [
  string, string, string, string, string, string, string, string, string, string, ...string[],
];
/** The tiers' names as the graph labels its directories, the namespaces' range, the label and the footnote. */
const TIER_NAMES = REST.slice(0, 4);
const RANGE = REST[4]!;
const LABEL = REST[5]!;
const NOTE = REST[6]!;
export const COPY: ConsoleCopy = {
  playground: PLAYGROUND, graph: MEMORY_GRAPH, namespaces: NAMESPACES_T, message: MESSAGE, retrieve: RETRIEVE, remember: REMEMBER,
  first: RANGE.split(' … ')[0]!,
};
export { TIER_NAMES, RANGE, LABEL, NOTE, HEAD_L, HEAD_R, INSTALL, CHIP_LINE };

// ------------------------------------------------------------------------------------------------ the world

/** The lens: the house's short tele (24° vertical). */
const FOV = 24;
const TAN_V = Math.tan(THREE.MathUtils.degToRad(FOV / 2)), TAN_H = TAN_V * (W / H);
/** The board: the two pages laid out in 1080p px at the split's framing; world metres per board px (a page's group is
 * scaled by BOARD_SCALE and holds panel px / 1000, as repo's terminal). */
const BOARD_SCALE = 0.4;
const K = BOARD_SCALE / 1000;
/** The pages: their left and right edges (board px), and how far each turns toward the spine (degrees). */
export const PAGE = { left: { x0: 112, x1: 902 }, right: { x0: 1018, x1: 1808 }, yaw: 9 } as const;
/** The headlines: their baseline (board px), em (px). */
const HEAD = { base: 236, em: 92, family: F.display(100, 600) } as const;
/** The terminal: its top (board px) and code size; it is as wide as its line, two rows tall (the line, the new prompt). */
const TERM = { y: 290, size: 19 } as const;
/** The cards on the right page (board px: left, top), their gap. */
const CARDS = { gap: 18, top: 290 } as const;
/** The divider down the spine: its top and bottom (board px), weight (px). */
const SPINE = { y0: 158, y1: 912, w: 1.4 } as const;
/** The field: world metres per tile px (a tile is 21 mm: a miniature, so the lens's depth of field reads across it), and
 * where it stands, well away from the pages. */
const FIELD_SCALE = 0.0001;
const FIELD_AT = new THREE.Vector3(40, 0, 0);
/** Ticks of the graph's simulation (the console's heat has cooled to about 1% by then: settled). */
const SIM_TICKS = 300;
/** The captions over the field (logical px): the label's and the footnote's mono px, baselines, typing speed. */
const CAPTION = { x: 112, label: { px: 27, base: 924 }, note: { px: 22, base: 968 }, cps: 110 } as const;

const INK = new THREE.Color().setRGB(...LIN.ink);
/** A sine ease in and out: the gentlest start and stop, for drifts. */
const inOutSine = (u: number) => 0.5 - 0.5 * Math.cos(Math.PI * clamp(u));
const unlit = (rgb: readonly [number, number, number], opts: THREE.MeshBasicMaterialParameters = {}) =>
  new THREE.MeshBasicMaterial({ color: new THREE.Color().setRGB(rgb[0], rgb[1], rgb[2]), ...opts });

interface Page {
  g: THREE.Group;
  /** Its centre (board px x): the group's origin and its turn's pivot. */
  cx: number;
}

interface Chip {
  place: ChipPlace;
  g: THREE.Group;
  label: THREE.Group;
  shadow: ChipShadow;
  check: Check | null;
  land: number;
  /** Rest and start (page-local units). */
  home: THREE.Vector3;
  from: THREE.Vector3;
}

export default class Anywhere extends Scene {
  private T!: Times;
  private stage!: Stage;
  private rig!: CameraRig;
  private scratch = new THREE.PerspectiveCamera(FOV, W / H, 0.005, 200);
  private left!: Page;
  private right!: Page;
  // the machine
  private term!: Panel;
  private termBox = { x: 0, y: 0, w: 0, h: 0 };
  private prompt!: Halo;
  private chips: Chip[] = [];
  private chipMat!: THREE.MeshPhysicalMaterial;
  private chipSweep!: SweepBand;
  private chipName!: THREE.MeshBasicMaterial;
  // the headlines
  private heads: { line: Headline; at: number[]; page: Page; x: number }[] = [];
  private heroMat!: THREE.MeshPhysicalMaterial;
  private heroSweep!: SweepBand;
  private flatMat!: THREE.MeshBasicMaterial;
  // the spine
  private spine!: THREE.Mesh;
  // the cloud
  private play!: Card;
  private graphCard!: Card;
  private nsCard!: Card;
  private cardHome = new Map<Card, THREE.Vector3>();
  private washes: Wash[] = [];
  private halos: Halo[] = [];
  private sim!: Sim;
  private graph!: GraphView;
  private tierLabels!: GlyphActors;
  private tierAtlas!: GlyphAtlas;
  private tierIdx: number[] = [];
  private backdrop!: Backdrop;
  // the field
  private field!: Field;
  private fieldG = new THREE.Group();
  private fieldFinal = { d: 1, az: 0, el: 0 };
  private fieldCentre = new THREE.Vector3();
  // the captions
  private layer = new Layer2D();
  private captionKey = '';
  // light
  private lights: THREE.Light[] = [];
  private mats: THREE.Material[] = [];

  override init() {
    const { renderer, vo, audio, start, end } = this.ctx;
    this.T = timesOf(vo, audio, start, end);
    this.stage = new Stage(renderer, { fov: FOV, near: 0.005, far: 200, envIntensity: 0.3 });
    this.left = this.page(PAGE.left);
    this.right = this.page(PAGE.right, -1);
    this.buildMachine();
    this.buildHeadlines();
    this.buildSpine();
    this.buildCloud();
    this.buildField();
    this.buildLights();
    this.backdrop = new Backdrop([4, 2.4]);
    this.backdrop.mesh.position.set(0, 0, -0.55);
    this.stage.scene.add(this.backdrop.mesh);
    this.rig = new CameraRig(this.keys());
    this.warmUp();
  }

  // ---------------------------------------------------------------------------------------------- the board

  /** A page: a group at its centre, turned toward the spine (`side` +1 the left page, -1 the right), scaled to px/1000. */
  private page(p: { x0: number; x1: number }, side = 1): Page {
    const cx = (p.x0 + p.x1) / 2, g = new THREE.Group();
    g.position.set((cx - 960) * K, 0, 0);
    g.rotation.y = THREE.MathUtils.degToRad(side * PAGE.yaw);
    g.scale.setScalar(BOARD_SCALE);
    this.stage.scene.add(g);
    return { g, cx };
  }

  /** Board px (x, y; z px toward the camera) on a page, in the page group's units. */
  private local(pg: Page, x: number, y: number, z = 0, target = new THREE.Vector3()) {
    return target.set((x - pg.cx) / 1000, (540 - y) / 1000, z / 1000);
  }

  /** Board px on a page, in the world. */
  private world(pg: Page, x: number, y: number, z = 0) {
    pg.g.updateMatrixWorld(true);
    return this.local(pg, x, y, z).applyMatrix4(pg.g.matrixWorld);
  }

  // ---------------------------------------------------------------------------------------------- the machine

  private buildMachine() {
    const T = this.T, pg = this.left;
    // the terminal, as wide as the install line, two rows: the line typed with her, the new prompt on Enter
    const lines: PanelLine[] = [
      { text: INSTALL, kind: 'cmd', at: T.type.at, cps: (Array.from(INSTALL).length - 3) / (T.type.end - T.type.at) },
      { text: '$', kind: 'cmd', at: T.enter },
    ];
    const g = panelLayout({ kind: 'terminal', size: TERM.size, lines });
    const w = Math.ceil(2 * g.padX + Array.from(INSTALL).length * g.adv);
    this.term = new Panel({ kind: 'terminal', w, rows: 2, size: TERM.size, lines, opaque: true });
    this.termBox = { x: PAGE.left.x0, y: TERM.y, w, h: this.term.spec.h };
    // the terminal's frame: its centre (the panel and the light on it share it)
    const termG = new THREE.Group();
    termG.position.copy(this.local(pg, this.termBox.x + w / 2, TERM.y + this.termBox.h / 2));
    termG.add(this.term.mesh);
    // the prompt's blood light, breathing while it waits
    this.prompt = new Halo(this.term.spec, 'bloodBright', 1.3 * TERM.size);
    termG.add(this.prompt.mesh);
    pg.g.add(termG);

    // the chips: satin panel2 under a clear coat (repo's), the names flat mono bone
    this.chipMat = new THREE.MeshPhysicalMaterial({
      color: new THREE.Color().setRGB(...LIN.panel2), roughness: 0.42, metalness: 0,
      clearcoat: 0.85, clearcoatRoughness: 0.1, sheen: 0.25, sheenRoughness: 0.5, sheenColor: new THREE.Color().setRGB(...LIN.boneDim),
    });
    this.chipSweep = withSweep(this.chipMat);
    this.chipName = unlit(LIN.bone);
    this.mats.push(this.chipMat, this.chipName);
    const places = layoutChipRows(chipNames(CHIP_LINE), PAGE.left.x0, TERM.y + this.termBox.h + 28, PAGE.left.x1 - PAGE.left.x0);
    places.forEach((place, i) => {
      const cg = new THREE.Group();
      const mesh = new THREE.Mesh(chipGeometry(place.w, CHIP.h, CHIP.r, CHIP.depth, CHIP.bevel), this.chipMat);
      const nameX = -place.w / 2 + CHIP.pad + (place.check ? 1.15 * CHIP.em : 0);
      const label = this.flatMono(place.name, CHIP.em, this.chipName);
      label.position.set(nameX, -0.365 * CHIP.em, 0.6);
      cg.add(mesh, label);
      let check: Check | null = null;
      if (place.check) {
        check = new Check(CHIP.em, -place.w / 2 + CHIP.pad - 0.05 * CHIP.em, -0.365 * CHIP.em, 0.8);
        cg.add(check.mesh);
      }
      const shadow = new ChipShadow(place.w, CHIP.h, CHIP.r, 36, 1 / 1000);
      const home = this.local(pg, place.x + place.w / 2, place.y + CHIP.h / 2);
      // behind the terminal: its middle, a hair behind its face
      const from = this.local(pg, place.x + place.w / 2, TERM.y + this.termBox.h * 0.45, -(CHIP.depth + 6));
      pg.g.add(cg, shadow.mesh);
      this.chips.push({ place, g: cg, label, shadow, check, land: this.T.chips[i]!, home, from });
    });
  }

  /** Flat mono type (her-type's flat: a sliver of depth, unlit), its origin the left end of its baseline, in px. */
  private flatMono(text: string, em: number, mat: THREE.Material) {
    const t = new Type3D(text, { family: F.mono(500), size: em, depth: 0.002, bevel: 0 }, mat);
    this.typeObjs.push(t);
    return t.group;
  }
  private typeObjs: Type3D[] = [];

  private poseMachine(t: number) {
    const T = this.T;
    this.term.draw(t);
    // the prompt breathes its blood light while it waits, and lets it go as the keys start
    const wait = 1 - prog(t, T.type.at - 0.1, T.type.at + 0.15);
    const o = this.term.cellOrigin(0, 0);
    this.prompt.set(o.x + 0.3 * this.term.adv, o.baseline - 0.36 * TERM.size, wait * (0.5 + 0.28 * Math.sin((2 * Math.PI * (t - T.start)) / (2 * T.beat))));
    for (const c of this.chips) {
      const d = dealAt(t, c.land);
      c.g.visible = d.on;
      c.shadow.mesh.visible = d.on;
      if (!d.on) continue;
      c.g.position.lerpVectors(c.from, c.home, d.s);
      c.g.rotation.set(-d.tilt, 0, 0);
      c.g.scale.setScalar(d.scale / 1000);
      const out = clamp(d.s);
      c.shadow.u.uOpacity.value = 0.55 * out;
      c.shadow.u.uBlur.value = 8 + 10 * out;
      c.shadow.mesh.position.copy(c.g.position).add(new THREE.Vector3(3 / 1000, -9 / 1000, -(CHIP.depth + 1) / 1000));
      // the ✔: the pen lands with the chip, hot at its head, the stroke lit as it lands and settling to flat moss
      if (c.check) {
        const pen = penAt(t, c.land + 0.05);
        c.check.set(pen, 0.42 + 1.6 * pulse(t, c.land + 0.05, 0.16), pen > 0 && pen < 1 ? 1 : 0);
      }
    }
    // a light glints across the chips as the last lands
    const first = this.chips[0]!, last = this.chips[this.chips.length - 1]!;
    const a = this.world(this.left, first.place.x - 80, first.place.y), b = this.world(this.left, PAGE.left.x1 + 60, first.place.y);
    sweepAt(this.chipSweep, t, [{ t0: last.land - 0.02, t1: last.land + 0.4, x0: a.x, x1: b.x, y: a.y }], { width: 46 * K, strength: 1.5 });
  }

  // ---------------------------------------------------------------------------------------------- the headlines

  private buildHeadlines() {
    const T = this.T;
    this.heroMat = Mat.satinBone();
    this.heroSweep = withSweep(this.heroMat);
    this.flatMat = unlit(LIN.bone);
    this.mats.push(this.heroMat, this.flatMat);
    // "On your machine…": On, your, machine (hero), on her onsets; the ellipsis is machine's
    const l = new Headline(HEAD_L, HEAD.family, HEAD.em / 1000, 2, this.heroMat, this.flatMat);
    // "or in my cloud.": they come up with the split (her "or" was in the dark before it), cloud (hero) on its onset
    const r = new Headline(HEAD_R, HEAD.family, HEAD.em / 1000, 3, this.heroMat, this.flatMat);
    this.heads.push(
      { line: l, at: [T.on, T.your, T.machine], page: this.left, x: PAGE.left.x0 },
      { line: r, at: [T.split + 0.05, Math.max(T.in, T.split + 0.12), T.my, T.cloud], page: this.right, x: PAGE.right.x0 },
    );
    for (const h of this.heads) {
      h.line.group.position.copy(this.local(h.page, h.x, HEAD.base));
      h.page.g.add(h.line.group);
    }
  }

  private poseHeadlines(t: number) {
    const sweeps: { t0: number; t1: number; x0: number; x1: number; y: number }[] = [];
    for (const h of this.heads) {
      h.line.pose(t, h.at);
      // a light along the hero word's bevels as it lands
      const [x0, x1] = h.line.span(h.line.hero), em = HEAD.em;
      const a = this.world(h.page, h.x + x0 * 1000 - em, HEAD.base - 0.35 * em), b = this.world(h.page, h.x + x1 * 1000 + em, HEAD.base - 0.35 * em);
      const at = h.at[h.line.hero]!;
      sweeps.push({ t0: at + 0.03, t1: at + 0.53, x0: a.x, x1: b.x, y: a.y });
    }
    sweepAt(this.heroSweep, t, sweeps, { width: 0.32 * HEAD.em * K, strength: 2.0 });
  }

  // ---------------------------------------------------------------------------------------------- the spine

  private buildSpine() {
    const mat = unlit(LIN.boneFaint, { transparent: true, opacity: 0.55, depthWrite: false });
    this.mats.push(mat);
    this.spine = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), mat);
    // where the pages' inner edges recede to
    const a = this.world(this.left, PAGE.left.x1, 540), b = this.world(this.right, PAGE.right.x0, 540);
    this.spine.position.set(0, ((540 - (SPINE.y0 + SPINE.y1) / 2) * K), (a.z + b.z) / 2);
    this.stage.scene.add(this.spine);
  }

  private poseSpine(t: number) {
    const T = this.T;
    // drawn down from its middle both ways on the split, fast, settling
    const k = prog(t, T.split - 0.02, T.split + 0.26, ease.outExpo);
    this.spine.visible = k > 0;
    this.spine.scale.set(SPINE.w * K, Math.max(1e-6, (SPINE.y1 - SPINE.y0) * K * k), 1);
  }

  // ---------------------------------------------------------------------------------------------- the cloud

  private buildCloud() {
    const pg = this.right, x0 = PAGE.right.x0, top = CARDS.top;
    this.play = new Card(PLAY.w, PLAY.h);
    this.graphCard = new Card(GRAPH.w, GRAPH.h);
    this.nsCard = new Card(NS.w, NS.h);
    const colX = x0 + PLAY.w + CARDS.gap;
    const place = (c: Card, x: number, y: number) => {
      const home = this.local(pg, x + c.w / 2, y + c.h / 2);
      c.group.position.copy(home);
      this.cardHome.set(c, home);
      pg.g.add(c.group);
    };
    place(this.play, x0, top);
    place(this.graphCard, colX, top);
    place(this.nsCard, colX, top + GRAPH.h + CARDS.gap);
    // the tool rows' light: a wash over each row and a halo at its wrench, moss for retrieve, blood for remember
    for (const k of [0, 1]) {
      const wash = new Wash(PLAY, glow(k === 0 ? 'moss' : 'bloodBright', 1));
      const halo = new Halo(PLAY, k === 0 ? 'moss' : 'bloodBright', 34);
      this.play.group.add(wash.mesh, halo.mesh);
      this.washes.push(wash);
      this.halos.push(halo);
    }
    // the Memory Graph: the console's simulation, run once, drawn over its card
    this.sim = simulate(memoryGraph(), SIM_TICKS);
    this.graph = new GraphView(this.sim, GRAPH, GRAPH.area);
    this.graphCard.group.add(this.graph.group);
    this.tierAtlas = new GlyphAtlas(TIER_NAMES.join(''), F.mono(500));
    this.tierLabels = new GlyphActors(64, this.tierAtlas);
    this.tierLabels.mesh.renderOrder = 4;
    this.graphCard.group.add(this.tierLabels.mesh);
    this.tierIdx = TIERS.map((tier) => this.sim.nodes.findIndex((n) => n.path === tier));
    if (TIERS.some((tier, i) => TIER_NAMES[i] !== tier)) throw new Error('anywhere: the tier labels are not the tiers');
  }

  /** The graph's fractional tick at t: its time speed-ramped, slow through the burst, quick through the long settle. */
  private tickAt(t: number) {
    const T = this.T, u = clamp((t - T.settle.at) / (T.settle.end - T.settle.at));
    return (this.sim.ticks.length - 1) * Math.pow(u, 2.4);
  }

  private poseCloud(t: number) {
    const T = this.T, tq = frameIdx(t) / FPS;
    // the cards deal in on their sixteenths: up from a little below and behind, settling with a hair of overshoot
    const deal = (c: Card, at: number) => {
      const s = slam(t, at, { freq: 4.4, damping: 0.74 });
      const home = this.cardHome.get(c)!;
      c.opacity = clamp(s * 2.2);
      c.group.position.copy(home).add(new THREE.Vector3(0, (-46 * (1 - s)) / 1000, (-60 * (1 - s)) / 1000));
      c.group.rotation.set((1 - s) * 0.18, 0, 0);
      return s;
    };
    deal(this.play, T.deal[0]!);
    deal(this.graphCard, T.deal[1]!);
    deal(this.nsCard, T.deal[2]!);
    // the Playground: the user's turn opens with the card; the tool rows on their beats; the caret blinks under them
    const ps: PlayState = {
      bubble: opening(t, T.deal[0]! + 0.08, 0.12),
      tools: [opening(t, T.retrieve - 0.06, 0.1), opening(t, T.remember - 0.06, 0.1)],
      caret: tq >= T.remember + 0.12 && Math.floor((frameIdx(t) - frameIdx(T.remember + 0.12)) / 9) % 2 === 0,
    };
    this.play.draw(playKey(ps), (c) => paintPlayground(c, COPY, ps));
    ([T.retrieve, T.remember] as const).forEach((at, k) => {
      const box = toolBox(k as 0 | 1, k === 0 ? RETRIEVE : REMEMBER);
      // the call runs: a band of its colour's light sweeps the row left to right, leading edge bright, and goes
      const run = prog(t, at - 0.06, at + 0.16, ease.outCubic), fadeOut = 1 - prog(t, at + 0.1, at + 0.42, ease.inOutQuad);
      this.washes[k]!.set(box.x, box.y, box.x + box.w * run, box.y + box.h, 0.05 * fadeOut, 0.5 * fadeOut * (run < 1 ? 1 : 0));
      this.halos[k]!.set(box.x + 12 + 15 + 8 + 7.5, box.y + box.h / 2, 1.1 * pulse(t, at, 0.16) * smootherstep(at - 0.06, at, t), 18);
    });
    // the Memory Graph
    this.graphCard.draw('g', (c) => paintGraph(c, COPY));
    const tick = this.tickAt(t), A = clamp((t - T.deal[1]!) * 6);
    const rel0 = T.settle.at + 0.55, relStep = 0.075;
    this.graph.set(tick, {
      alpha: A,
      draw: (r) => prog(t, rel0 + r * relStep, rel0 + r * relStep + 0.22, ease.outCubic),
      lit: (r) => pulse(t, rel0 + r * relStep + 0.22, 0.2) + 0.5 * pulse(t, T.memory, 0.25),
    });
    this.poseTierLabels(tick, A);
    // Namespaces: the first namespace on "One"
    const first = opening(t, T.first, 0.12);
    this.nsCard.draw(`n${Math.round(first * 1000)}`, (c) => paintNamespaces(c, COPY, { first }));
  }

  /** The tiers' names beside their directories, riding with them (the console labels a directory beside its node). */
  private poseTierLabels(tick: number, alpha: number) {
    const L = this.tierLabels, em = 15;
    L.begin();
    const p = { x: 0, y: 0 }, right = new THREE.Vector3(em / 1000, 0, 0), up = new THREE.Vector3(0, em / 1000, 0);
    this.tierIdx.forEach((i, k) => {
      this.graph.at(tick, i, p);
      const name = TIER_NAMES[k]!, r = 8 * Math.max(0.75, Math.min(1.3, this.graph.k));
      Array.from(name).forEach((ch, j) => {
        const x = p.x + r + 5 + j * 0.6 * em, y = p.y + 0.36 * em;
        L.add({
          origin: this.graphCard.local(x, y, 0.6), right, up,
          glyph: [this.tierAtlas.of(ch), -1, 0, 0],
          color: [LIN.boneDim[0], LIN.boneDim[1], LIN.boneDim[2], 0.95 * alpha],
        });
      });
    });
    L.end();
  }

  // ---------------------------------------------------------------------------------------------- the field

  private buildField() {
    this.field = new Field();
    this.fieldG.add(this.field.group);
    this.fieldG.position.copy(FIELD_AT);
    this.fieldG.scale.setScalar(FIELD_SCALE);
    this.stage.scene.add(this.fieldG);
    // the final framing: the whole field, turned, high in the frame over the captions
    this.fieldFinal = { d: this.fieldDistance(64, 32, 1), az: 19, el: 14 };
  }

  /** The block's extent after a continuous count of doublings along x and y (field px). */
  private block(nx: number, ny: number) {
    const w = 2 ** nx * PITCH.x - TILE.gap, h = 2 ** ny * PITCH.y - TILE.gap;
    return { cx: w / 2, cy: -h / 2, w, h };
  }

  /** The camera's distance (m) that frames a block of `cols` by `rows`, by how far it is along the doubling (0..1). */
  private fieldDistance(cols: number, rows: number, along: number) {
    const b = this.block(Math.log2(cols), Math.log2(rows));
    const fillW = lerp(0.36, 0.9, along), fillH = lerp(0.42, 0.7, along);
    return Math.max((b.w * FIELD_SCALE) / (2 * TAN_H * fillW), (b.h * FIELD_SCALE) / (2 * TAN_V * fillH));
  }

  /** Doublings done by t along x and along y, eased into each so the camera anticipates a hair. */
  private doubled(t: number) {
    let nx = 0, ny = 0;
    this.T.doublings.forEach((d, k) => {
      const s = smootherstep(d - 0.11, d + 0.05, t);
      if (k % 2 === 0) nx += s;
      else ny += s;
    });
    return { nx, ny, n: nx + ny };
  }

  /** The field's camera at t: framing the block as it doubles, pulling back √2 a doubling and turning a little. */
  private fieldCam(cam: THREE.PerspectiveCamera, t: number) {
    const T = this.T, { nx, ny, n } = this.doubled(t), along = n / DOUBLINGS;
    const b = this.block(nx, ny);
    const hold = prog(t, T.doublings[DOUBLINGS - 1]!, T.end, ease.linear);
    const d0 = this.fieldDistance(1, 1, 0), d1 = this.fieldFinal.d;
    const d = d0 * Math.pow(d1 / d0, along) * (1 + 0.05 * hold);
    const az = THREE.MathUtils.degToRad(lerp(3, this.fieldFinal.az, inOutSine(along)) + 1.5 * hold);
    const el = THREE.MathUtils.degToRad(lerp(2, this.fieldFinal.el, inOutSine(along)));
    const centre = new THREE.Vector3(b.cx * FIELD_SCALE, b.cy * FIELD_SCALE, 0).add(FIELD_AT);
    this.fieldCentre.copy(centre);
    const back = new THREE.Vector3(Math.sin(az) * Math.cos(el), Math.sin(el), Math.cos(az) * Math.cos(el));
    cam.position.copy(centre).addScaledVector(back, d);
    // the field rides high in the frame as it grows, over the captions
    const bias = lerp(0, 0.16, along) * d * TAN_V;
    const target = centre.clone().add(new THREE.Vector3(0, -bias, 0));
    cam.up.set(0, 1, 0);
    cam.lookAt(target);
    cam.rotateZ(THREE.MathUtils.degToRad(lerp(-0.6, -2.6, along)));
    cam.fov = FOV;
    cam.updateProjectionMatrix();
    cam.updateMatrixWorld();
    return { centre, d };
  }

  private poseField(t: number) {
    const T = this.T;
    const last = T.doublings[DOUBLINGS - 1]!;
    // a light runs across the whole field as the last doubling settles
    const span = 64 * PITCH.x + 0.35 * 32 * PITCH.y;
    const u = prog(t, last + 0.12, last + 0.75, ease.inOutQuad);
    const sweep: [number, number, number] = u > 0 && u < 1 ? [lerp(-0.1, 1.1, u) * span, 900, 0.1 * Math.sin(Math.PI * u)] : [0, 1, 0];
    // a tile's name and icon go as they get too small to read, leaving the tiles and their edges: the boundaries
    const d = this.stage.camera.position.distanceTo(this.fieldCentre);
    const emPx = (TILE.em * FIELD_SCALE * H) / (2 * d * TAN_V);
    this.field.set({ t, land: T.doublings, fade: 1, sweep, detail: smootherstep(4.5, 9, emPx) });
  }

  // ---------------------------------------------------------------------------------------------- the camera

  /** A key looking at board point (x, y) on a page's plane, `width` board px across the frame, from az/el (degrees). */
  private frame(t: number, x: number, y: number, width: number, az: number, el: number, roll = 0, e?: (u: number) => number): CamKey {
    const target = new THREE.Vector3((x - 960) * K, (540 - y) * K, 0);
    const d = (width * K) / 2 / TAN_H;
    const a = THREE.MathUtils.degToRad(az), b = THREE.MathUtils.degToRad(el);
    const pos = target.clone().add(new THREE.Vector3(Math.sin(a) * Math.cos(b), Math.sin(b), Math.cos(a) * Math.cos(b)).multiplyScalar(d));
    return { t, pos: pos.toArray() as V3, target: target.toArray() as V3, fov: FOV, roll, ease: e };
  }

  private keys(): CamKey[] {
    const T = this.T;
    return [
      // the machine: in close on the left page, a little low and from the left of square, drifting in along the line
      this.frame(T.start, 470, 356, 1060, 4, -3, -1.2),
      this.frame(T.type.end, 540, 352, 960, 6.5, -2, -0.8, inOutSine),
      this.frame(T.split, 505, 392, 1010, 7.5, -1.2, -0.6, ease.inOutCubic),
      // the split: on the downbeat the camera whips back and right onto both pages, settling into the spread
      this.frame(T.split + 0.34, 960, 540, 1920, 0, 1.5, 0, ease.outExpo),
      // into the cloud: a slow drift right and in, as the cards come alive
      this.frame(T.remember, 1050, 548, 1810, -2.2, 1.6, 0.3, inOutSine),
      this.frame(T.cut, 1210, 590, 1540, -4.5, 2.2, 0.7, inOutSine),
    ];
  }

  /** Focus as a focus ring turns (diopters between keys): the terminal, then card to card across the cloud. */
  private focus(t: number) {
    const T = this.T, st = this.stage;
    const inv = (p: THREE.Vector3) => 1 / Math.max(0.05, st.depthOf(p));
    const tb = this.termBox;
    const term = this.world(this.left, tb.x + tb.w * 0.4, tb.y + tb.h / 2);
    const playC = this.world(this.right, PAGE.right.x0 + PLAY.w * 0.4, CARDS.top + 200);
    const graphC = this.world(this.right, PAGE.right.x0 + PLAY.w + CARDS.gap + GRAPH.w / 2, CARDS.top + GRAPH.h / 2);
    const nsC = this.world(this.right, PAGE.right.x0 + PLAY.w + CARDS.gap + NS.w / 2, CARDS.top + GRAPH.h + CARDS.gap + 90);
    const ks: [number, number, ((x: number) => number)?][] = [
      [T.start, inv(term)],
      [T.split, inv(term)],
      [T.split + 0.3, inv(playC), ease.inOutCubic],
      [T.remember - 0.1, inv(playC)],
      [T.remember + 0.35, inv(graphC), ease.inOutCubic],
      [T.first - 0.15, inv(graphC)],
      [T.first + 0.3, inv(nsC), ease.inOutCubic],
    ];
    const fstop = keys(t, [[T.split, 3.2], [T.split + 0.3, 5.6, ease.inOutCubic]]);
    return { focus: 1 / keys(t, ks), fstop };
  }

  // ---------------------------------------------------------------------------------------------- light

  /**
   * Neutral light only (lit bone stays out of the bloom's chroma gate), for the headlines and the chips (the panels and
   * cards are unlit): a long softbox overhead and in front whose reflection runs along the top bevels (her's), a key from
   * the upper left, a low fill, a hard rim from behind on the right that edges the walls.
   */
  private buildLights() {
    const s = this.stage.scene;
    initAreaLights();
    const head = new THREE.Vector3(0, (540 - HEAD.base) * K, 0);
    const top = new THREE.RectAreaLight(0xffffff, 5.5, 1.6, 0.36);
    top.position.set(0, head.y + 0.36, 0.42);
    top.lookAt(0, head.y, -0.02);
    const key = new THREE.DirectionalLight(0xffffff, 1.6);
    key.position.set(-1.0, 1.4, 1.9);
    key.target.position.set(0, 0, 0);
    const fill = new THREE.DirectionalLight(0xffffff, 0.3);
    fill.position.set(1.4, -0.3, 1.2);
    fill.target.position.set(0, 0, 0);
    const rim = new THREE.DirectionalLight(0xffffff, 3.0);
    rim.position.set(1.2, 1.1, -1.6);
    rim.target.position.set(0, 0, 0);
    s.add(top, key, key.target, fill, fill.target, rim, rim.target);
    this.lights.push(top, key, fill, rim);
  }

  // ---------------------------------------------------------------------------------------------- render

  /**
   * Draw everything once before the first frame: shaders compile for the stage's target, the panels and cards paint and
   * upload. Nothing it sets outlives it: render() sets all state from t.
   */
  private warmUp() {
    const st = this.stage, rt = makeRT(W, H), T = this.T;
    const culled: THREE.Object3D[] = [];
    st.scene.traverse((o) => {
      if (o.frustumCulled) (o.frustumCulled = false), culled.push(o);
    });
    this.rig.apply(st.camera, T.split + 0.5);
    this.poseMachine(T.chips[3]! + 0.2);
    this.poseHeadlines(T.cloud + 0.3);
    this.poseSpine(T.split + 0.5);
    this.poseCloud(T.remember + 0.05);
    this.poseField(T.doublings[DOUBLINGS - 1]!);
    for (const c of this.chips) c.g.visible = c.shadow.mesh.visible = true;
    this.fieldG.visible = true;
    st.compile();
    st.render(rt, { dof: { focus: 1, fstop: 4 } });
    for (const o of culled) o.frustumCulled = true;
    rt.dispose();
  }

  render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides {
    const t = f.t, T = this.T, st = this.stage, r = this.ctx.renderer;
    // the shot is the frame's, not the sub-frame's: the cut sits half way between two frames, where no shutter reaches
    const inField = t >= T.cut;
    this.left.g.visible = this.right.g.visible = this.spine.visible = !inField;
    this.backdrop.mesh.visible = !inField;
    this.fieldG.visible = inField;
    let dof: { focus: number; fstop: number };
    if (!inField) {
      this.rig.apply(st.camera, t);
      this.poseMachine(t);
      this.poseHeadlines(t);
      this.poseSpine(t);
      this.poseCloud(t);
      dof = this.focus(t);
      // the studio turns slowly, swinging a little on the split, so its softboxes slide across the satin
      st.scene.environmentRotation.set(0, 0.16 * (t - T.start) + 0.5 * smootherstep(T.split, T.split + 0.5, t), 0);
      const pool = this.stage.camera.position;
      this.backdrop.set(pool.x * 0.6, 0.02, 1.4, 0.7, 0.18);
    } else {
      const { d } = this.fieldCam(st.camera, t);
      this.poseField(t);
      dof = { focus: d, fstop: keys(t, [[T.doublings[0]!, 4], [T.doublings[DOUBLINGS - 1]!, 2.2, inOutSine]]) };
    }
    const cc = r.getClearColor(new THREE.Color()), ca = r.getClearAlpha();
    r.setClearColor(INK, 1);
    st.render(out, { dof });
    r.setClearColor(cc, ca);

    if (inField) {
      this.drawCaptions(t);
      this.ctx.comp.draw(r, this.layer.texture, out);
    }

    // the split and the cut punch in a hair; the chips' landings jolt the frame
    let zoom = 0.006 * pulse(t, T.split, 0.12) + 0.004 * pulse(t, T.down, 0.1);
    for (const d of T.doublings) zoom += 0.0012 * pulse(t, d, 0.06);
    let shake = 0;
    for (const at of T.chips) if (t >= at && t < T.split) shake += 1.1 * Math.exp(-(t - at) * 26) * Math.cos((t - at) * 2 * Math.PI * 11);
    return { zoom: 1 + zoom, shake: [0, shake] };
  }

  /** The label and the footnote, typing on the output frame grid. Repainted only when a character lands. */
  private drawCaptions(t: number) {
    const T = this.T, tq = frameIdx(t) / FPS;
    const n = (at: number, s: string) => Math.floor(clamp((tq - at) * CAPTION.cps + 1, 0, Array.from(s).length));
    const nl = n(T.label, LABEL), nn = n(T.note, NOTE);
    const key = `${nl}|${nn}`;
    if (key === this.captionKey) return;
    this.captionKey = key;
    const c = this.layer.ctx;
    this.layer.clear();
    c.textBaseline = 'alphabetic';
    c.font = font(F.mono(500), CAPTION.label.px);
    c.fillStyle = rgba('bone', 0.94);
    c.fillText(Array.from(LABEL).slice(0, nl).join(''), CAPTION.x, CAPTION.label.base);
    c.font = font(F.mono(400), CAPTION.note.px);
    c.fillStyle = rgba('boneDim');
    c.fillText(Array.from(NOTE).slice(0, nn).join(''), CAPTION.x, CAPTION.note.base);
    this.layer.upload();
  }

  override dispose() {
    this.term?.dispose();
    this.prompt?.dispose();
    for (const c of this.chips) {
      (c.g.children[0] as THREE.Mesh).geometry.dispose();
      c.shadow.dispose();
      c.check?.dispose();
    }
    for (const t of this.typeObjs) t.dispose();
    for (const h of this.heads) h.line.dispose();
    this.spine?.geometry.dispose();
    for (const c of [this.play, this.graphCard, this.nsCard]) c?.dispose();
    for (const w of this.washes) w.dispose();
    for (const h of this.halos) h.dispose();
    this.graph?.dispose();
    this.tierLabels?.dispose();
    this.tierAtlas?.dispose();
    this.backdrop?.dispose();
    this.field?.dispose();
    for (const m of this.mats) m.dispose();
    this.layer.dispose();
    this.stage?.dispose();
  }
}
