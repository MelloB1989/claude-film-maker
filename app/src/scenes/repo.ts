// Scene 04 `repo`: "I'm just a git repo." / "You already know how to read me." (Plan 2 Task 14; spec §4 04.) She shows
// that her memory is a real git repository, and the joke is that the beautiful part is literal.
//
// One world and one camera, every time from the data (her measured onsets, the score's beats):
// 1. The terminal. A tilted 3D terminal hangs in the dark; the camera pushes in and round it, focus riding the typing
//    head as `$ cd ~/memory && ls` types in with "I'm just a…". On the downbeat as she reaches "git repo" the listing
//    pops out of the output row as four chips, `facts/` `incidents/` `rules/` `skills/` (repo-chips.ts), one a 32nd
//    note, with weight: each launches from inside the panel's face, lands on its note with a heavy overshoot and rights
//    itself, its shadow spreading under it, the panel taking the kick; a light glints across them on "repo".
// 2. The dive. `$ git log --oneline` types in the pause; on Enter the camera dives into the output row and through the
//    terminal's face ("you can cd into it"), the chips flying past the lens, the panel melting away.
// 3. The log as a string of beads. Behind the terminal the diff thread runs across the dark, and the log prints as
//    glass commit beads (engine/bead.ts), one a beat from "You", newest first as git log prints, each landing nearer the
//    camera than the last: so the string reads in time from left to right, history to HEAD (3f9a1c2, her bead), and
//    every bead in close-up has the ones before it receding behind it. Each glides in along the thread past the lens
//    with its moss light riding inside it, lands on its beat with a click, blooms, sends the light running out along
//    the thread both ways and keeps an ember of it (the thread's strand light); its oneline entry types in under it, and the lines
//    printed before it step back with their beads, so the log reads back into the dark. The camera tracks along the
//    string bead to bead, racking focus to each as it glides in; a softbox's reflection slides over each as it lands.
// 4. The file. On "read" the footnote types in, low on the left: Nothing about that is a metaphor — you can cd into
//    it. As the last bead lands on "me." the camera pulls back to the whole string; on the next beat the file itself,
//    facts/people/user.md (spec §11.4, line numbers and all), swings in over its far end on a hinge, the beads going to
//    bokeh behind it.
// 5. The exit (transitions/repo-loom.ts, a match along the thread): the pull-back lands the string on the screen line of
//    loom's first fell (B05's track at loom's first frame, repo-exit.ts), and on the last beat its moss light runs out
//    from HEAD along it both ways, reaching the frame's edges on the cut, where the string becomes loom's weft.
import * as THREE from 'three';
import { Scene, disposeLayer, type Frame, type PostOverrides } from '../engine/scene';
import { CameraRig, Stage, freeTransmission, initAreaLights, type CamKey, type V3 } from '../engine/stage';
import { Layer2D, W, H, makeRT } from '../engine/gl';
import { Panel, lineEnd, type PanelLine } from '../engine/panels';
import { DIFF_THREAD, Thread, envelopeOf, strandFlare, type StrandGlow } from '../engine/thread3d';
import { Bead, beadGeometry } from '../engine/bead';
import { Type3D } from '../engine/type3d';
import { F, font } from '../engine/type';
import { LIN, rgba } from '../engine/palette';
import { slam } from '../engine/motion';
import { sweepAt, withSweep, type SweepBand } from '../engine/sweep';
import { clamp, ease, keys, lerp, prog, pulse } from '../engine/util';
import { ChipShadow, chipGeometry, chipPop, layoutChips, recoil, type ChipSpec } from './repo-chips';
import { Track } from '../engine/track';
import { exitError, fitLine, lineThrough, solve2, type Px, type ScreenLine } from './repo-exit';
import { DIRS, LOG, terminalLines, timesOf } from './repo-time';
import S from './repo.strings.json';

export { LOG, timesOf };

// ------------------------------------------------------------------------------------------------ the copy

const [, , , ...REST] = S as string[];
const PATH = REST[4]!;
/** The memory file's non-empty lines (spec §11.4), and the footnote (§11.9). */
const MEMORY = REST.slice(5, 18);
const FOOTNOTE = REST[18]!;
/** The file's 18 lines: its non-empty lines, and the blank ones between them (-1). */
export const FILE: PanelLine[] = [0, 1, 2, 3, 4, 5, -1, 6, 7, -1, 8, -1, 9, -1, 10, -1, 11, 12].map((i) => ({ text: i < 0 ? '' : MEMORY[i]! }));

type Times = ReturnType<typeof timesOf>;

// ------------------------------------------------------------------------------------------------ the world (metres)

/** The lens: a short tele (24° vertical fov, a 48 mm on the full-frame gate). */
const FOV = 24;
/** World units per terminal px (the panel mesh is w/1000 world units; its group is scaled by this). */
const TERM_SCALE = 0.4;
const TPX = TERM_SCALE / 1000;
/** The terminal: panel px; its code size. */
const TERM = { w: 900, h: 300, size: 30 };
/** Where along the output row the dive goes in (a fraction of the panel's width). */
const DIVE_X = 0.37;
/** The chips: height (of the row), padding round the name, the gap between, corner radius, depth and bevel, how far
 * out of the face they pop, the names' em (panel px). */
const CHIP = { h: 46, pad: 15, gap: 16, r: 13, depth: 12, bevel: 3, lift: 46, em: 26 };
/** The thread and its beads (her's sizes: the look matches the bead she showed). */
const THREAD_R = 0.0042;
const BEAD_R = 0.024;
/**
 * The string behind the terminal, in the dive's frame: its first bead's place (m behind the terminal's face, along the
 * dive), the angle it recedes at to the right (degrees off square to the dive), how much it bows away from the camera
 * (m at 1 m from the first bead), and its ends (m along it from the first bead: off the frame's left, into the dark).
 */
const STRING = { depth: 0.62, angle: 36, bow: 0.05, from: -1.25, to: 0.9 };
/**
 * Where the beads rest along the string (m from the first). The log prints newest first and each commit lands nearer
 * the camera than the last, so the string reads in time from left to right: 105ca74, a41c9d0, 8b21e04, then HEAD,
 * 3f9a1c2, deepest.
 */
const SLOTS = [0, -0.1, -0.2, -0.3];
/** How far each commit glides in from (m back along the thread: from the near side, past the lens), and its spring (the
 * house's tight kind: in about an eighth of a second, a 4.6% overshoot, the click). */
const GLIDE = { travel: 0.24, freq: 4, damping: 0.7 };
/** The camera on a bead in close-up: out from the string (toward the terminal), along it (−: left), up (m); where the
 * bead sits in frame (half-frame fractions from the centre, +x right, +y up). */
const BEAD_CAM = { off: 0.34, along: -0.05, up: 0.05, sx: -0.3, sy: 0.08 };
/** The pull-back off the last bead: its distance (in close-ups), its rise (m), and how much the camera breathes in over
 * the file's hold (a fraction of it). */
const PULL = { back: 1.62, lift: 0.02, breathe: 0.035 };
/** How far the engraving's band rises above the bore's equator (radians): over dark glass, not the refracted thread. */
const ETCH_RISE = 0.42;
/** A label: its em (frame px at its bead's close-up); its left end and baseline from the bead's centre (bead radii in
 * frame, right and down); how fast it types in (characters a second); its strength once the next commit has landed
 * (the lines printed before stay, receding with their beads: the log reads back into the dark). */
const LABEL = { px: 28, dx: -0.92, dy: 1.5, cps: 200, after: 0.4 };
/** Where the focus holds a bead in close-up, and its label sits: its near face, this many radii toward the camera. */
const FACE = 0.8;
/** The file: panel px, code size; where its centre lands in frame (px), its height there (px), its distance (m). */
const FILE_SPEC = { w: 640, h: 774, size: 24 };
const FILE_AT = { x: 1480, y: 520, hpx: 690, dist: 0.4 };
/** Its swing on the hinge (radians, from nearly edge-on to a few degrees open) and its timing: it starts `lead` before
 * the beat and decelerates into place over `dur`, all but there on the beat (a reveal, not a slam). */
const FILE_SWING = { from: 1.42, to: 0.1, dur: 0.36, lead: 0.24 };
/** loom's shot: its track has the fell (fell_l, fell_r) the string lands on for the cut. */
const LOOM_SHOT = 'b05_loom';
/**
 * The exit light: the moss runs out from HEAD's bead along the string both ways, from `from` of the way between the
 * file's landing and the cut, reaching both ends on the cut, accelerating (`n` lights per side, `level` of the lit level).
 */
const EXIT = { from: 0.45, n: 24, level: 0.85 };

/** The footnote: mono px, its baseline's left end (frame px), typing speed. */
const NOTE = { px: 24, x: 150, y: 958, cps: 95 };

const Y = new THREE.Vector3(0, 1, 0);
const INK = new THREE.Color().setRGB(...LIN.ink);
const unlit = (rgb: readonly [number, number, number], opts: THREE.MeshBasicMaterialParameters = {}) =>
  new THREE.MeshBasicMaterial({ color: new THREE.Color().setRGB(rgb[0], rgb[1], rgb[2]), ...opts });
/** Flat type: a sliver of depth (em), no bevel. */
const FLAT = { depth: 0.002, bevel: 0 } as const;

interface Commit {
  bead: Bead;
  /** Rest arc fraction, landing time. */
  u: number;
  at: number;
  /** Its place on the thread at rest; the thread's direction there (on into the dark); the side the camera sees it from
   * (square to the thread, level, toward the terminal); and the bore's direction that stands its etched hash upright
   * seen from there. */
  pos: THREE.Vector3;
  tangent: THREE.Vector3;
  side: THREE.Vector3;
  axis: THREE.Vector3;
  label: Type3D;
  labelLen: number;
  /** The label's origin from its bead's centre (world), set at the close-up. */
  labelAt: THREE.Vector3;
  /** The label's own materials (it fades on its own): the hash's and the message's. */
  labelMats: THREE.MeshBasicMaterial[];
}

/**
 * A commit's bead on a thread `len` m long at t (arc fraction): gliding in along it from GLIDE.travel nearer the camera,
 * landing on `at` (the spring first reaches its mark then and overshoots a hair: the click). `s` is the spring.
 */
export function glideU(t: number, u: number, at: number, len: number): { u: number; s: number } {
  const s = slam(t, at, { freq: GLIDE.freq, damping: GLIDE.damping });
  return { u: u - (GLIDE.travel / len) * (1 - s), s };
}

/** The file's swing at t, 0..1, landing on `land`: it starts FILE_SWING.lead before and decelerates into place. */
export function fileSwing(t: number, land: number): number {
  return prog(t, land - FILE_SWING.lead, land - FILE_SWING.lead + FILE_SWING.dur, ease.outQuart);
}

/** The moss a landed commit keeps inside its bead (envelope level): the string of commits stays moss-lit. */
export const EMBER = 0.3;
/** The light a landing sends out along the thread both ways: its speed (m/s), level, life (s), width (bead cores). */
const RIPPLE = { speed: 0.42, level: 0.9, life: 0.8, width: 1.25 };

/**
 * The moss light on a thread `len` m long at t, for commits landing at `at` on `u` (arc fractions): riding in inside
 * its bead, blooming as it lands, running out both ways along the thread, and an ember left in the bead.
 */
export function commitGlows(t: number, commits: readonly { u: number; at: number }[], len: number): StrandGlow[] {
  const core = (0.75 * BEAD_R) / len, out: StrandGlow[] = [];
  for (const c of commits) {
    const g = glideU(t, c.u, c.at, len);
    if (g.s <= 0) continue;
    if (t < c.at) out.push({ u: g.u, w: core, k: 0.35 + 0.45 * clamp(g.s) });
    const bloom = strandFlare(t, c.at, { lead: 0.04, decay: 0.7 });
    if (bloom > 0) out.push({ u: g.u, w: core * 1.15, k: bloom });
    const dt = t - c.at;
    if (dt > 0) {
      const run = (RIPPLE.speed * dt) / len, k = RIPPLE.level * Math.max(0, 1 - dt / RIPPLE.life) ** 2;
      if (k > 0) out.push({ u: c.u - run, w: core * RIPPLE.width, k }, { u: c.u + run, w: core * RIPPLE.width, k });
      out.push({ u: g.u, w: core, k: EMBER + 0.12 * Math.exp(-dt / 0.5) });
    }
  }
  return out;
}

export default class Repo extends Scene {
  private T!: Times;
  private stage!: Stage;
  private rig!: CameraRig;
  private scratch = new THREE.PerspectiveCamera(FOV, W / H, 0.01, 30);
  // the terminal
  private term!: Panel;
  private termG = new THREE.Group();
  private chips: { spec: ChipSpec; g: THREE.Group; mesh: THREE.Mesh; label: Type3D; shadow: ChipShadow; home: THREE.Vector3; land: number }[] = [];
  private chipMat!: THREE.MeshPhysicalMaterial;
  private chipSweep!: SweepBand;
  /** The dive's aim on the panel (world), the panel's normal, the dive's direction. */
  private O = new THREE.Vector3();
  private N = new THREE.Vector3();
  private D = new THREE.Vector3();
  // the string
  private thread!: Thread;
  private beadGeo!: THREE.BufferGeometry;
  private commits: Commit[] = [];
  // the file
  private file!: Panel;
  private fileHinge = new THREE.Group();
  private fileRest = new THREE.Quaternion();
  // the footnote
  private layer = new Layer2D();
  private noteKey = '';
  // lights
  private kicker!: THREE.RectAreaLight;
  private kick!: THREE.RectAreaLight;
  private mats: THREE.Material[] = [];
  /** loom's first fell on screen, and the middle of its stretch in frame (px): where the string lands for the cut. */
  private fell!: ScreenLine;
  private fellX = 0;

  override async init() {
    const { renderer, vo, audio, start, end } = this.ctx;
    // loom's first fell, at loom's first frame (the frame the cut lands on)
    const loom = await Track.load(LOOM_SHOT), F = Math.ceil(end * 30) / 30;
    const fl = loom.at('fell_l', F), fr = loom.at('fell_r', F);
    this.fell = lineThrough(fl, fr);
    this.fellX = (clamp(Math.min(fl.x, fr.x), 0, W) + clamp(Math.max(fl.x, fr.x), 0, W)) / 2;
    this.T = timesOf(vo, audio, start, end);
    this.stage = new Stage(renderer, { fov: FOV, near: 0.01, far: 30, envIntensity: 0.22 });
    this.buildTerminal();
    this.buildString();
    this.buildFile();
    this.buildLights();
    this.rig = new CameraRig(this.alignExit(this.keys()));
    this.placeLabels();
    this.placeFile();
    this.warmUp();
  }

  // ---------------------------------------------------------------------------------------------- the terminal

  /** Row r's top (panel px) with every row above it open. */
  private rowTop(r: number) {
    return this.term.rowTop(r);
  }

  private lineH() {
    return this.term.lineH;
  }

  /** A point on the terminal (panel px from its top left; z px in front of its face), in the world. */
  private termPoint(x: number, y: number, z = 0) {
    this.termG.updateMatrixWorld(true);
    return new THREE.Vector3((x - TERM.w / 2) / 1000, (TERM.h / 2 - y) / 1000, z / 1000).applyMatrix4(this.termG.matrixWorld);
  }

  private buildTerminal() {
    const T = this.T;
    const lines = terminalLines(T), cd = lines[0]!, log = lines[2]!;
    this.term = new Panel({ kind: 'terminal', w: TERM.w, h: TERM.h, size: TERM.size, lines });
    if (Math.abs(lineEnd(cd) - T.cd.end) > 1e-6 || Math.abs(lineEnd(log) - T.log.end) > 1e-6) throw new Error('repo: a command does not finish typing when it should');
    this.termG.scale.setScalar(TERM_SCALE);
    this.termG.rotation.set(-0.03, 0, 0);
    this.termG.add(this.term.mesh);
    this.stage.scene.add(this.termG);

    // the chips: one material (satin panel2 under a clear coat), the names in flat bone
    this.chipMat = new THREE.MeshPhysicalMaterial({
      color: new THREE.Color().setRGB(...LIN.panel2), roughness: 0.42, metalness: 0,
      clearcoat: 0.85, clearcoatRoughness: 0.1, sheen: 0.25, sheenRoughness: 0.5, sheenColor: new THREE.Color().setRGB(...LIN.boneDim),
    });
    this.chipSweep = withSweep(this.chipMat);
    const name = unlit(LIN.bone);
    this.mats.push(this.chipMat, name);
    // (the listing's row is the chips': they start where its text would)
    const specs = layoutChips(DIRS, this.term.textOrigin(1).x, 0.6 * CHIP.em, CHIP.pad, CHIP.gap);
    const row = this.rowTop(1) + this.lineH() / 2;
    specs.forEach((spec, i) => {
      // in panel px: the group scales them into the panel's space (its mesh is w/1000 wide)
      const g = new THREE.Group();
      const mesh = new THREE.Mesh(chipGeometry(spec.w, CHIP.h, CHIP.r, CHIP.depth, CHIP.bevel), this.chipMat);
      const label = new Type3D(spec.name, { family: F.mono(500), size: CHIP.em, ...FLAT }, name);
      label.group.position.set(-spec.w / 2 + CHIP.pad, -0.33 * CHIP.em, 0.6);
      g.add(mesh, label.group);
      const home = new THREE.Vector3((spec.x + spec.w / 2 - TERM.w / 2) / 1000, (TERM.h / 2 - row) / 1000, 0);
      const shadow = new ChipShadow(spec.w, CHIP.h, CHIP.r, 40, 1 / 1000);
      this.termG.add(g, shadow.mesh);
      this.chips.push({ spec, g, mesh, label, shadow, home, land: T.chips[i]! });
    });
    // the dive aims at the output row under `git log`, below the command's middle
    this.O.copy(this.termPoint(DIVE_X * TERM.w, this.rowTop(3) + this.lineH() / 2));
    this.N.set(0, 0, 1).applyQuaternion(this.termG.quaternion);
  }

  private poseTerminal(t: number) {
    const T = this.T;
    // the panel melts away as the camera reaches its face
    const gap = this.stage.camera.position.clone().sub(this.O).dot(this.N);
    this.term.opacity = t < T.cross + 0.05 ? clamp((gap - 0.012) / 0.05) : 0;
    this.term.mesh.visible = this.term.opacity > 0;
    // it takes the kick of each chip's launch
    this.termG.position.copy(this.N).multiplyScalar(-recoil(t, T.chips) * CHIP.lift * TPX);
    if (this.term.mesh.visible) this.term.draw(t);
    for (const c of this.chips) {
      const p = chipPop(t, c.land);
      const on = p.on && this.term.mesh.visible;
      c.g.visible = c.shadow.mesh.visible = on;
      if (!on) continue;
      // from inside the face (half its depth back) out to its height, tipped back and righting
      c.g.position.copy(c.home).setZ((-0.5 * CHIP.depth + (CHIP.lift + 0.5 * CHIP.depth) * p.lift) / 1000);
      c.g.rotation.set(-p.tilt, 0, 0);
      c.g.scale.setScalar(p.scale / 1000);
      const lift = Math.max(0, p.lift);
      c.shadow.u.uOpacity.value = 0.62 * clamp(lift * 1.4) * this.term.opacity;
      c.shadow.u.uBlur.value = 4 + 22 * lift;
      c.shadow.mesh.position.set(c.home.x + (4 * lift) / 1000, c.home.y - (10 * lift) / 1000, 0.0004);
    }
    // a light glints across the chips on "repo"
    const a = this.chips[0]!, b = this.chips[this.chips.length - 1]!;
    const x0 = this.termPoint(a.spec.x - 60, 0).x, x1 = this.termPoint(b.spec.x + b.spec.w + 60, 0).x, y = this.termPoint(0, this.rowTop(1)).y;
    sweepAt(this.chipSweep, t, [{ t0: T.repo, t1: T.repo + 0.42, x0, x1, y }], { width: 40 * TPX, strength: 1.6 });
  }

  // ---------------------------------------------------------------------------------------------- the string

  /** The dive's frame: forward (into the terminal), right, up. */
  private diveFrame() {
    const f = this.D.clone(), r = new THREE.Vector3().crossVectors(f, Y).normalize(), u = new THREE.Vector3().crossVectors(r, f);
    return { f, r, u };
  }

  /**
   * The thread's centreline: across the dive STRING.depth behind the terminal's face (hidden by the panel from the
   * terminal shot), receding to the right at STRING.angle and bowing gently away from the camera, from off the frame's
   * left into the dark.
   */
  private threadPoints(): THREE.Vector3[] {
    const { f, r } = this.diveFrame(), a = THREE.MathUtils.degToRad(STRING.angle);
    const along = r.clone().multiplyScalar(Math.cos(a)).addScaledVector(f, Math.sin(a));
    const toward = f.clone().multiplyScalar(-Math.cos(a)).addScaledVector(r, Math.sin(a)); // square to it, toward the terminal
    const P1 = this.O.clone().addScaledVector(f, STRING.depth), pts: THREE.Vector3[] = [];
    for (let x = STRING.from; x <= STRING.to + 1e-9; x += 0.19) pts.push(P1.clone().addScaledVector(along, x).addScaledVector(toward, -STRING.bow * x * x));
    return pts;
  }

  private buildString() {
    const T = this.T;
    // the dive runs from the terminal shot's last key into the output row and on through the panel
    const k = this.terminalKeys();
    this.D.copy(this.O).sub(new THREE.Vector3(...k[k.length - 1]!.pos)).normalize();
    this.thread = new Thread(this.threadPoints(), { ...DIFF_THREAD, radius: THREAD_R, fuzz: 0.6 });
    // both strands rest; the strand light lights the moss strand along its length, from rest up to the lit level
    this.thread.setStrandGlow({ blood: DIFF_THREAD.rest, moss: DIFF_THREAD.rest });
    this.thread.setStrandLight({}, DIFF_THREAD.glow);
    this.stage.scene.add(this.thread.mesh);

    // each bead's place, and the frame it is seen in from the camera on its close-up
    const x0 = -STRING.from;
    const places = SLOTS.map((m) => {
      const u = (x0 + m) / (STRING.to - STRING.from), fr = this.thread.frameAt(u);
      const side = new THREE.Vector3().crossVectors(Y, fr.tangent).normalize();
      if (side.dot(this.D) > 0) side.negate();
      // the bore runs so that the face (toward the camera) and it make an upright frame: y = face × bore = up
      return { u, pos: fr.pos, tangent: fr.tangent, side, axis: new THREE.Vector3().crossVectors(Y, side) };
    });
    // one bead shape for all four, its engraving centred where the camera sees each from in close-up (the camera's
    // place in the bead's frame: along its bore, out from its face, up), each its own etched hash (so its own material)
    const p0 = places[0]!, cam = this.beadEye(p0);
    const off = cam.clone().sub(p0.pos);
    const look: [number, number] = [Math.atan2(off.dot(p0.axis), off.dot(p0.side)), Math.atan2(off.y, Math.hypot(off.dot(p0.axis), off.dot(p0.side))) + ETCH_RISE];
    const shape = { radius: BEAD_R, bore: THREAD_R * 1.3, chamfer: THREAD_R * 0.7, centre: look };
    this.beadGeo = beadGeometry(shape);
    LOG.forEach((entry, i) => {
      const bead = new Bead({ ...shape, text: entry.hash }, { geometry: this.beadGeo });
      this.stage.scene.add(bead.mesh);
      const hashLen = Array.from(entry.hash).length;
      const labelMats = [unlit(LIN.boneDim, { transparent: true }), unlit(LIN.bone, { transparent: true })];
      const label = new Type3D(entry.line, { family: F.mono(400), size: 1, ...FLAT }, (g) => labelMats[g.i < hashLen ? 0 : 1]!);
      this.stage.scene.add(label.group);
      this.commits.push({ bead, ...places[i]!, at: T.beads[i]!, label, labelLen: Array.from(entry.line).length, labelMats, labelAt: new THREE.Vector3() });
    });
  }

  /** The camera's place on a bead in close-up. */
  private beadEye(c: { pos: THREE.Vector3; tangent: THREE.Vector3; side: THREE.Vector3 }, k = 1, lift = 0) {
    return c.pos.clone().addScaledVector(c.side, BEAD_CAM.off * k).addScaledVector(c.tangent, BEAD_CAM.along * k).addScaledVector(Y, BEAD_CAM.up * k + lift);
  }

  /**
   * Each oneline entry under its bead: set in the plane through the bead square to the camera at its close-up, LABEL.px
   * a frame px there (smaller if it would run past the title-safe right edge), its left end and baseline where LABEL
   * puts them from the bead in frame.
   */
  private placeLabels() {
    for (const c of this.commits) {
      const cam = this.camAt(c.at + 0.3);
      const px = this.pxAt(cam, c.pos), r = BEAD_R / px; // world units per frame px at the bead, its radius in frame px
      const sx = (c.pos.clone().project(cam).x + 1) * (W / 2), left = sx + LABEL.dx * r;
      const em = Math.min(LABEL.px, (W - 96 - left) / (0.6 * c.labelLen));
      const size = em * px;
      c.label.setSize(size);
      const right = new THREE.Vector3(1, 0, 0).applyQuaternion(cam.quaternion), up = new THREE.Vector3(0, 1, 0).applyQuaternion(cam.quaternion);
      c.label.group.quaternion.copy(cam.quaternion);
      // in the plane of the bead's near face, where the focus holds it (and its etched hash)
      c.labelAt.copy(right).multiplyScalar(LABEL.dx * BEAD_R).addScaledVector(up, -LABEL.dy * BEAD_R).addScaledVector(c.side, FACE * BEAD_R);
    }
  }

  /** World units per frame px at a point's depth, for a camera. */
  private pxAt(cam: THREE.PerspectiveCamera, p: THREE.Vector3) {
    const depth = -p.clone().applyMatrix4(cam.matrixWorldInverse).z;
    return (depth * 2 * Math.tan(THREE.MathUtils.degToRad(cam.fov) / 2)) / H;
  }

  private poseString(t: number) {
    const T = this.T, th = this.thread, len = th.length();
    // the thread draws on behind the terminal from Enter (the panel hides it), whole by the time the camera is through
    th.setDraw(0, keys(t, [[T.enter, 0], [T.cross, 1, ease.outQuad]]));
    this.thread.setStrandLight({ moss: envelopeOf([...commitGlows(t, this.commits, len), ...this.exitGlows(t)]) });
    this.commits.forEach((c, i) => {
      const g = glideU(t, c.u, c.at, len);
      c.bead.mesh.visible = g.s > 0 && t > T.enter;
      if (c.bead.mesh.visible) {
        c.bead.place(th.pointAt(g.u), c.axis, c.side, (1 - g.s) * 1.3);
        c.bead.mesh.scale.setScalar(clamp(g.s * 6)); // it grows in from the dark over its first frames
      }
      // its label rides with it (through the click's overshoot)
      c.label.group.position.copy(c.bead.mesh.visible ? c.bead.mesh.position : c.pos).add(c.labelAt);
      // its log line types in under it as it lands, steps back as the next lands (it stays, receding with its bead), and
      // gives way to the file
      const n = Math.floor(clamp((t - c.at - 0.04) * LABEL.cps, -1, c.labelLen));
      const next = this.commits[i + 1];
      const k = (next ? 1 - (1 - LABEL.after) * prog(t, next.at - 0.05, next.at + 0.2, ease.inOutQuad) : 1) * (1 - prog(t, T.fileLand - 0.3, T.fileLand - 0.05, ease.inOutQuad));
      c.label.group.visible = n >= 0 && k > 0;
      for (const gl of c.label.glyphs) gl.mesh.visible = gl.i <= n;
      for (const m of c.labelMats) m.opacity = k;
    });
  }

  /**
   * The exit light: from HEAD's bead, a lit span runs out along the string both ways, accelerating, so it reaches both
   * ends of the thread on the cut. The brightest thing in frame then, it is where loom's weft shows through first.
   */
  private exitGlows(t: number): StrandGlow[] {
    const T = this.T, head = this.commits[this.commits.length - 1]!, t0 = lerp(T.fileLand, T.end, EXIT.from);
    const k = prog(t, t0, T.end, ease.inCubic);
    if (k <= 0) return [];
    const reach = k * Math.max(head.u, 1 - head.u), w = reach / EXIT.n + 1e-4, out: StrandGlow[] = [];
    for (let i = 0; i <= EXIT.n; i++) {
      const d = (reach * i) / EXIT.n, lv = EXIT.level * (0.55 + 0.45 * k);
      out.push({ u: head.u - d, w, k: lv }, { u: head.u + d, w, k: lv });
    }
    return out;
  }

  /**
   * The string on screen at t through a rig: the thread's points in front of the camera and in frame, over the fell's
   * stretch (px).
   */
  private stringOnScreen(rig: CameraRig, t: number): Px[] {
    const cam = this.scratch, out: Px[] = [], p = new THREE.Vector3();
    rig.apply(cam, t);
    cam.updateMatrixWorld();
    const x0 = clamp(this.fellX * 2 - W, 0, W);
    for (let i = 0; i <= 400; i++) {
      this.thread.pointAt(i / 400, p);
      if (-p.clone().applyMatrix4(cam.matrixWorldInverse).z <= 0) continue;
      const v = p.project(cam), x = (v.x + 1) * (W / 2), y = (1 - v.y) * (H / 2);
      if (x >= x0 && x <= W && y >= 0 && y <= H) out.push({ x, y });
    }
    return out;
  }

  /**
   * The pull-back's last two keys turned (roll) and tilted (their target raised or lowered) by the same amounts, so that
   * at the cut the string lies on loom's first fell: its angle within 0.05°, its height within half a px at the middle
   * of the fell's stretch. The file is placed after this, through the same rig, so it keeps its place in frame.
   */
  private alignExit(keys: CamKey[]): CamKey[] {
    const T = this.T, n = keys.length, ends = new Set([n - 2, n - 1]);
    const shifted = ([dr, dv]: [number, number]) =>
      keys.map((k, i): CamKey => (ends.has(i) ? { ...k, roll: (k.roll ?? 0) + dr, target: [k.target[0], k.target[1] + dv, k.target[2]] } : k));
    const err = (p: [number, number]) => exitError(fitLine(this.stringOnScreen(new CameraRig(shifted(p)), T.end)), this.fell, this.fellX);
    const p = solve2(err, [0, 0], [0.05, 0.0005], [THREE.MathUtils.degToRad(0.05), 0.5]);
    return shifted(p);
  }

  // ---------------------------------------------------------------------------------------------- the file

  private buildFile() {
    this.file = new Panel({ kind: 'editor', title: PATH, w: FILE_SPEC.w, h: FILE_SPEC.h, lang: 'md', gutter: 'numbers', size: FILE_SPEC.size, lines: FILE });
    // hinged on its left edge
    this.file.mesh.position.x = FILE_SPEC.w / 2000;
    this.fileHinge.add(this.file.mesh);
    this.stage.scene.add(this.fileHinge);
  }

  /** Where the file lands: framed by the camera as it is once the file has settled, nearer than any bead. */
  private placeFile() {
    const T = this.T, cam = this.camAt(T.fileLand + 0.35);
    const px = (FILE_AT.dist * 2 * Math.tan(THREE.MathUtils.degToRad(cam.fov) / 2)) / H;
    const scale = (FILE_AT.hpx * px) / (FILE_SPEC.h / 1000);
    const right = new THREE.Vector3(1, 0, 0).applyQuaternion(cam.quaternion), up = new THREE.Vector3(0, 1, 0).applyQuaternion(cam.quaternion);
    const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(cam.quaternion);
    const centre = cam.position.clone().addScaledVector(fwd, FILE_AT.dist).addScaledVector(right, (FILE_AT.x - W / 2) * px).addScaledVector(up, (H / 2 - FILE_AT.y) * px);
    this.fileHinge.scale.setScalar(scale);
    this.fileHinge.quaternion.copy(cam.quaternion);
    this.fileHinge.position.copy(centre).addScaledVector(right, (-FILE_SPEC.w / 2000) * scale);
    this.fileRest.copy(this.fileHinge.quaternion);
  }

  private poseFile(t: number) {
    const T = this.T;
    const s = fileSwing(t, T.fileLand);
    this.file.mesh.visible = s > 0;
    if (!this.file.mesh.visible) return;
    // a door swinging toward us on its left hinge: from nearly edge-on (its right side far away) to a few degrees open
    const yaw = lerp(FILE_SWING.from, FILE_SWING.to, s);
    this.fileHinge.quaternion.copy(this.fileRest).multiply(new THREE.Quaternion().setFromAxisAngle(Y, yaw));
    this.file.opacity = clamp(s * 3);
    this.file.draw(t);
  }

  // ---------------------------------------------------------------------------------------------- the camera

  /** A key looking at `at` from azimuth and elevation (degrees, round world y from +z) and distance. */
  private orbit(t: number, at: THREE.Vector3, az: number, el: number, d: number, o: Partial<CamKey> = {}): CamKey {
    const a = THREE.MathUtils.degToRad(az), b = THREE.MathUtils.degToRad(el);
    const back = new THREE.Vector3(Math.sin(a) * Math.cos(b), Math.sin(b), Math.cos(a) * Math.cos(b));
    return { t, pos: at.clone().addScaledVector(back, d).toArray() as V3, target: at.toArray() as V3, ...o };
  }

  /** The terminal shot's keys (they also set the dive's direction: its last key looks down it). */
  private terminalKeys(): CamKey[] {
    const T = this.T, mid = this.lineH() / 2;
    const cmd = this.termPoint(this.term.cellOrigin(0, 9).x, this.rowTop(0) + mid);
    const chips = this.termPoint(this.term.cellOrigin(1, 16).x, this.rowTop(1) + mid, CHIP.lift * 0.6);
    // a slow push and turn while she types; on the downbeat the camera snaps in onto the chips as they pop and drifts
    // on them while the light crosses them; then it turns down the line of the dive as `git log` is entered
    return [
      { ...this.orbit(T.start, this.termPoint(0.4 * TERM.w, this.rowTop(1)), -32, 7.5, 0.5), fov: FOV, roll: -2.5 },
      this.orbit(T.pop - 0.02, cmd.clone().lerp(chips, 0.3), -28, 6, 0.44, { roll: -2, ease: ease.linear }),
      this.orbit(T.pop + 0.3, chips, -23, 4.5, 0.37, { roll: -1.2, ease: ease.outCubic }),
      this.orbit(T.repo + 0.3, chips, -21.5, 4.2, 0.355, { roll: -1.1, ease: ease.linear }),
      this.orbit(T.enter, this.O, -18, 3, 0.36, { roll: -1, ease: ease.inOutCubic }),
    ];
  }

  /** A target that puts `p` at (sx, sy) of the half-frame from the centre, for a camera at `eye`. */
  private aim(eye: THREE.Vector3, p: THREE.Vector3, sx: number, sy: number, fov = FOV) {
    const dir = p.clone().sub(eye), dist = dir.length();
    dir.normalize();
    const right = new THREE.Vector3().crossVectors(dir, Y).normalize(), up = new THREE.Vector3().crossVectors(right, dir);
    const ty = Math.tan(THREE.MathUtils.degToRad(fov) / 2), tx = ty * (W / H);
    return p.clone().addScaledVector(right, -sx * tx * dist).addScaledVector(up, -sy * ty * dist);
  }

  private keys(): CamKey[] {
    const T = this.T, keys = this.terminalKeys(), O = this.O, d = this.D;
    // the dive: accelerating into the output row, through the face, then easing out beside the first bead
    keys.push({ t: T.cross, pos: O.clone().addScaledVector(d, -0.012).toArray() as V3, target: O.clone().addScaledVector(d, 1).toArray() as V3, ease: ease.inCubic });
    const view = (c: Commit, k = 1, lift = 0, at = c.pos, sx = BEAD_CAM.sx, sy = BEAD_CAM.sy): { pos: V3; target: V3 } => {
      const eye = this.beadEye(c, k, lift);
      return { pos: eye.toArray() as V3, target: this.aim(eye, at, sx, sy).toArray() as V3 };
    };
    // the track: settling on each bead as it lands (it reads as its line types in), gliding on to the next
    this.commits.forEach((c, i) => keys.push({ t: c.at + 0.16, ...view(c), roll: -3 - 0.6 * i, ease: i === 0 ? ease.outCubic : ease.inOutCubic }));
    // on "me." the camera dollies straight back off the last bead (it keeps its place in frame, so nothing smears) and
    // the whole string opens out to the right of it, history to HEAD; the file lands over its far end, and the camera
    // only breathes in while it holds
    const last = this.commits[this.commits.length - 1]!;
    keys.push({ t: T.fileLand - 0.06, ...view(last, PULL.back, PULL.lift), roll: -3.6, ease: ease.inOutCubic });
    keys.push({ t: T.end, ...view(last, PULL.back * (1 - PULL.breathe), PULL.lift), roll: -3.8, ease: ease.linear });
    return keys;
  }

  /** A scratch camera where the rig has the stage's at t. */
  private camAt(t: number) {
    this.rig.apply(this.scratch, t);
    return this.scratch;
  }

  // ---------------------------------------------------------------------------------------------- lights

  private buildLights() {
    const s = this.stage.scene, { f, r } = this.diveFrame(), mid = this.O.clone().addScaledVector(f, STRING.depth).addScaledVector(r, 0.15);
    // neutral light only (lit bone stays out of the bloom's chroma gate), her's set for the thread and the bead: a key
    // from the upper left, a softbox in front of it, a hard rim from behind the string that sculpts the plies, a kicker
    // behind the bead in close-up that rings its edge out of the ink, and a small softbox that swings over each bead as
    // it lands
    initAreaLights();
    const box = new THREE.RectAreaLight(0xffffff, 0.35, 1.8, 0.6);
    box.position.copy(mid).addScaledVector(f, -1.4).addScaledVector(r, -0.9).addScaledVector(Y, 1.2);
    box.lookAt(mid);
    const key = new THREE.DirectionalLight(0xffffff, 0.3);
    key.position.copy(mid).addScaledVector(f, -1.6).addScaledVector(r, -1.2).addScaledVector(Y, 2.0);
    key.target.position.copy(mid);
    const rim = new THREE.DirectionalLight(0xffffff, 5);
    rim.position.copy(mid).addScaledVector(f, 2.2).addScaledVector(r, 1.2).addScaledVector(Y, 1.4);
    rim.target.position.copy(mid);
    this.kicker = new THREE.RectAreaLight(0xffffff, 0, 0.34, 0.34);
    this.kick = new THREE.RectAreaLight(0xffffff, 0, 0.02, 0.1);
    s.add(box, key, key.target, rim, rim.target, this.kicker, this.kick);
  }

  /** The kicker behind the bead in close-up, and the kick swinging over each bead as it lands. */
  private poseLights(t: number) {
    const cam = this.stage.camera;
    // the bead in close-up: the last to have landed (or the one landing)
    let hero = this.commits[0]!;
    for (const c of this.commits) if (t >= c.at - 0.3) hero = c;
    const hp = hero.bead.mesh.position, on = hero.bead.mesh.visible;
    const away = hp.clone().sub(cam.position).normalize();
    const side = new THREE.Vector3().crossVectors(away, Y).normalize();
    this.kicker.intensity = on ? 26 : 0;
    this.kicker.position.copy(hp).addScaledVector(away, 0.24).addScaledVector(side, 0.12).addScaledVector(Y, 0.12);
    this.kicker.lookAt(hp);
    const kk = prog(t, hero.at - 0.05, hero.at + 0.5, ease.inOutQuad);
    this.kick.intensity = on ? 150 * Math.sin(Math.PI * kk) : 0;
    const dir = away.clone().negate().applyAxisAngle(Y, lerp(-0.9, 0.9, kk));
    this.kick.position.copy(hp).addScaledVector(dir, 0.24).addScaledVector(Y, 0.15);
    this.kick.lookAt(hp);
  }

  // ---------------------------------------------------------------------------------------------- render

  /**
   * Draw everything once before the first frame: shaders compile for the stage's target, textures and geometry upload,
   * and three makes the glass's transmission target. Nothing it sets outlives it: render() sets all state from t.
   */
  private warmUp() {
    const st = this.stage, rt = makeRT(W, H), T = this.T;
    const culled: THREE.Object3D[] = [];
    st.scene.traverse((o) => {
      if (o.frustumCulled) (o.frustumCulled = false), culled.push(o);
    });
    this.rig.apply(st.camera, T.chips[3]! + 0.3);
    this.poseTerminal(T.chips[3]! + 0.3);
    this.rig.apply(st.camera, T.end);
    this.poseString(T.end);
    this.poseFile(T.end);
    this.term.mesh.visible = true;
    for (const c of this.chips) c.g.visible = c.shadow.mesh.visible = true;
    st.compile();
    st.render(rt, { dof: { focus: 0.3, fstop: 4 } });
    for (const o of culled) o.frustumCulled = true;
    rt.dispose();
  }

  render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides {
    const t = f.t, T = this.T, st = this.stage;
    this.rig.apply(st.camera, t);
    this.poseTerminal(t);
    this.poseString(t);
    this.poseFile(t);
    this.poseLights(t);

    const r = this.ctx.renderer, cc = r.getClearColor(new THREE.Color()), ca = r.getClearAlpha();
    r.setClearColor(INK, 1); // what the glass sees through the transmission pass
    st.render(out, { dof: this.focus(t) });
    r.setClearColor(cc, ca);

    if (t >= T.note) {
      this.drawNote(t);
      this.ctx.comp.draw(r, this.layer.texture, out);
    }

    // the chips' landings jolt the frame a hair; each commit and the file punch in
    let shake = 0, zoom = 0;
    for (const at of T.chips) if (t >= at) shake += 1.6 * Math.exp(-(t - at) * 24) * Math.cos((t - at) * 2 * Math.PI * 10);
    for (const at of T.beads) zoom += 0.004 * pulse(t, at, 0.09);
    zoom += 0.005 * pulse(t, T.fileLand, 0.12);
    return { shake: [0, shake], zoom: 1 + zoom };
  }

  /** Focus as a focus ring turns (diopters): the typing head, the chips, through the dive to each bead's mark, the file. */
  private focus(t: number) {
    const T = this.T, st = this.stage;
    const inv = (p: THREE.Vector3) => 1 / Math.max(0.03, st.depthOf(p));
    const mid = this.lineH() / 2;
    const head = (row: number, at: number, end: number) => this.termPoint(this.term.cellOrigin(row, 2 + 17 * clamp((t - at) / (end - at))).x, this.rowTop(row) + mid);
    const chip = this.chips[1]!;
    const ks: [number, number, ((x: number) => number)?][] = [
      [T.cd.at, inv(head(0, T.cd.at, T.cd.end))],
      [T.cd.end, inv(head(0, T.cd.at, T.cd.end)), ease.linear],
      [T.pop + 0.2, inv(this.termPoint(chip.spec.x + chip.spec.w, this.rowTop(1) + mid, CHIP.lift)), ease.inOutCubic],
      [T.log.at + 0.1, inv(head(2, T.log.at, T.log.end)), ease.inOutCubic],
      [T.log.end, inv(head(2, T.log.at, T.log.end)), ease.linear],
    ];
    // each bead's mark, its near face: the bead glides into focus
    for (const c of this.commits) ks.push([c.at - 0.17, ks[ks.length - 1]![1]], [c.at + 0.02, inv(c.pos.clone().addScaledVector(c.side, FACE * BEAD_R)), ease.inOutCubic]);
    ks.push([T.fileLand - 0.16, ks[ks.length - 1]![1]], [T.fileLand + 0.02, inv(this.file.mesh.getWorldPosition(new THREE.Vector3())), ease.inOutCubic]);
    const fstop = t < T.cross - 0.05 ? 2.8 : t < T.fileLand - 0.16 ? 4 : 6;
    return { focus: 1 / keys(t, ks), fstop };
  }

  /** The footnote, typing in on "read": mono, bone-dim, low on the left. Redrawn only when a character lands. */
  private drawNote(t: number) {
    const n = Math.floor(clamp((t - this.T.note) * NOTE.cps + 1, 0, Array.from(FOOTNOTE).length));
    if (String(n) === this.noteKey) return;
    this.noteKey = String(n);
    const c = this.layer.ctx;
    this.layer.clear();
    c.font = font(F.mono(400), NOTE.px);
    c.fillStyle = rgba('boneDim');
    c.fillText(Array.from(FOOTNOTE).slice(0, n).join(''), NOTE.x, NOTE.y);
    this.layer.upload();
  }

  override dispose() {
    const r = this.ctx.renderer;
    if (this.commits[0]) freeTransmission(r, this.commits[0].bead.material);
    this.term?.dispose();
    for (const c of this.chips) {
      c.mesh.geometry.dispose();
      c.label.dispose();
      c.shadow.dispose();
    }
    this.thread?.dispose();
    for (const c of this.commits) {
      c.bead.dispose();
      c.label.dispose();
      for (const m of c.labelMats) m.dispose();
    }
    this.beadGeo?.dispose();
    this.file?.dispose();
    for (const m of this.mats) m.dispose();
    disposeLayer(this.layer);
    this.stage?.dispose();
  }
}
