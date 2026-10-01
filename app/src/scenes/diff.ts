// Scene 06 `diff`: "Change your mind?" / "I'll change mine." / "We'll always have the diff." (Plan 2 Task 16; spec §4
// 06.) Memory is versioned, so nothing is lost; and the romance is that she keeps the old line.
//
// One world, one camera, every time from the data (her measured onsets, the score's beats; diff-time.ts):
// 1. The file. The editor Panel of facts/people/user.md (repo's file at its size, its line numbers, now with the diff's
//    sign column, in a 16-row window) hangs in the dark in close 3D at 8b21e04: `confidence: 0.6`, `Uses VS Code.`. On
//    "Change" the caret glides down the file, the camera craning with it, and lands on `Uses VS Code.` on the downbeat;
//    on "mind?" the line is selected, and the selection stirs on the next beat.
// 2. The strike. On "I'll" a blade of blood light (diff-fx.ts) launches along the line and cuts through it at full speed,
//    its head white-hot, the camera driving in with it, into the impact on "change": the panel takes the blow, the frame
//    jolts, a flare of blood light breaks round the words, the `−` lands, a blood sign lights in the margin (gitsigns'
//    column) and the cut cools to an ember. A quick second cut takes `confidence: 0.6`. On "mine." the camera eases
//    back as both new rows open, `confidence: 0.9` and `Uses neovim. Has since 2019.`, the line written in with her by a
//    small moss light riding its typing head, moss signs beside both.
// 3. The diff. On the downbeat the camera whips down and the history dock rises under the editor (diff-dock.ts):
//    `$ gitloom diff facts/people/user.md 8b21e04 3f9a1c2`, its stat typing out `1 file changed, 2 insertions(+),
//    2 deletions(-)`, and the scrubber: the diff thread drawn across the dark with the file's commits strung on it as glass
//    beads, the playhead on HEAD.
// 4. Time travel. After "We'll" the playhead runs back to 8b21e04 on a speed ramp, the thread's blood strand lit, and
//    the file rewinds with it (its clock is the playhead's): neovim untypes, the rows close, the cut runs back out of the
//    line white-hot, and `Uses VS Code.` stands whole again as the playhead lands on the beat, slowing into it. It holds
//    there through "always"; then runs forward, moss lit, the blade cutting again, home into the beat on "have". The lens
//    strains with the playhead's speed (its fringes open), the camera leaning toward the past and back.
// 5. The romance. "…the diff.": everything slows. The camera, pushing in since "We'll", comes round into a slow 3/4
//    close-up of the two lines, the aperture opening until only they hold, the dock sinking away; a warm pool of light on
//    them, the rest of the file falling into shadow, and the old line's cut glowing faintly in blood, breathing, a memory.
import * as THREE from 'three';
import { Scene, type Frame, type PostOverrides } from '../engine/scene';
import { CameraRig, Stage, freeTransmission, initAreaLights, type CamKey } from '../engine/stage';
import { W, H, makeRT } from '../engine/gl';
import { Panel, panelLayout, type PanelLine } from '../engine/panels';
import { DIFF_THREAD, strandFlare } from '../engine/thread3d';
import { LIN } from '../engine/palette';
import { LOOK } from '../engine/look';
import { slam } from '../engine/motion';
import { FPS, clamp, ease, frameIdx, keys, lerp, prog, pulse } from '../engine/util';
import { bladeHeat, docTime, historyAt, romance, struckAt, timesOf, type Times } from './diff-time';
import { Bar, Blade, Halo, Spot, Wash } from '../engine/panel-light';
import { Backdrop, fitKey } from './diff-fx';
import { DOCK, Dock } from './diff-dock';
import S from './diff.strings.json';

// ------------------------------------------------------------------------------------------------ the copy

const [PATH, DASH, TIER, TAGS, CONF_OLD, CONF_NEW, UPDATED, DARK, SHIPS, EDITOR, VSCODE, NEOVIM, TZ, IST, WORKS, CMD, STAT, H105, HA41, H8B, H3F, MSG_OLD, MSG_NEW] =
  S as string[] as [string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string];
const len = (s: string) => Array.from(s).length;

/** The file's rows: §11.4 at 8b21e04 (`confidence: 0.6`, `Uses VS Code.`), each change a deletion and its addition. */
export const ROW = { confOld: 3, confNew: 4, old: 13, neo: 14 } as const;

/** The editor's lines, timed by the file's clock (the strikes and the additions; the rest is there throughout). */
export function fileLines(T: Pick<Times, 'strike' | 'conf' | 'add' | 'addEnd'>): PanelLine[] {
  return [
    { text: DASH }, { text: TIER }, { text: TAGS },
    { text: CONF_OLD, kind: 'del', at: T.conf.at, cps: len(CONF_OLD) / (T.conf.end - T.conf.at) },
    { text: CONF_NEW, kind: 'add', at: T.add },
    { text: UPDATED }, { text: DASH }, { text: '' },
    { text: DARK }, { text: SHIPS }, { text: '' },
    { text: EDITOR }, { text: '' },
    { text: VSCODE, kind: 'del', at: T.strike.at, cps: len(VSCODE) / (T.strike.end - T.strike.at) },
    { text: NEOVIM, kind: 'add', at: T.add, cps: (len(NEOVIM) - 1) / (T.addEnd - T.add) },
    { text: '' }, { text: TZ }, { text: '' }, { text: IST }, { text: WORKS },
  ];
}

/** The history the dock shows, oldest first (repo's log); the diff's two commits carry their messages. */
export const HISTORY = [{ hash: H105 }, { hash: HA41 }, { hash: H8B, msg: MSG_OLD }, { hash: H3F, msg: MSG_NEW }];
const OLD = 2, HEAD = 3;

// ------------------------------------------------------------------------------------------------ the editor (panel px)

/** The editor: repo's file (640 wide at 24 px code), its window 16 rows tall: the file down to line 16, and once the
 * two added rows have opened, down to line 14 (an editor's viewport: the rows below the diff scroll out of it). */
const SIZE = 24;
/** The editor's layout, the Panel's own for its spec (an editor with a numbers gutter and the diff's sign column): the
 * layout reads only the file's lines' kinds and count, so they come untimed here. */
const G = panelLayout({ kind: 'editor', size: SIZE, gutter: 'numbers', lines: fileLines({ strike: { at: 0, end: 1 }, conf: { at: 0, end: 1 }, add: 0, addEnd: 1 }) });
/** 16 rows, and below the last a margin that stops short of the next row's glyphs (they start 10.5 px into a row). */
const ROWS = 16;
export const EDIT = { w: 640, h: G.bar + G.padTop + ROWS * G.lineH + 9 };
/** Where the diff's signs stand in the left margin (gitsigns' column), x px. */
const SIGN_X = 11;

// ------------------------------------------------------------------------------------------------ the world (metres)

/** The lens: repo's short tele. */
const FOV = 24;
/** World units per editor px ×1000 (the editor's group scale): the file is 26 cm wide, its code 9.6 mm to the em. */
const EDIT_SCALE = 0.4;
/** The caret's landing: a small, firm settle (its wobble's frequency, Hz, and decay rate, 1/s). */
const LAND = { freq: 5, decay: 16 };
/** The blade on `Uses VS Code.`: its core's half-thickness and its light's reach across (px); the confidence's. */
const BLADE = { core: 1.4, halo: 10 };
const BLADE_SMALL = { core: 1.1, halo: 7 };
/** The ember a cut cools to (glow level, just over the bloom's opening). */
const EMBER = 1.16;
/** The diff's signs: their level on the event and at rest. */
const SIGN = { flare: 2.6, rest: 1.3 };
/** How hard the panel takes the blow (px back along its normal) and its ring (Hz). */
const KICK = { px: 10, freq: 4.2 };

const INK = new THREE.Color().setRGB(...LIN.ink);

export default class Diff extends Scene {
  private T!: Times;
  private stage!: Stage;
  private rig!: CameraRig;
  private edit!: Panel;
  private editG = new THREE.Group();
  private caret!: THREE.Mesh;
  private band!: Wash;
  private selection!: Wash;
  private flash!: Halo;
  private blade!: Blade;
  private bladeConf!: Blade;
  /** The diff's signs: the struck rows' blood bars and the added rows' moss bars. */
  private signs!: { old: Bar; neo: Bar; confOld: Bar; confNew: Bar };
  private spot!: Spot;
  /** The old line's aura in the romance: a faint blood light behind its words. */
  private aura!: Halo;
  /** The moss light that rides the typing head of the added line. */
  private pen!: Halo;
  private dock!: Dock;
  private backdrop!: Backdrop;
  private kicker!: THREE.RectAreaLight;
  private mats: THREE.Material[] = [];

  override init() {
    const { renderer, vo, audio, start, end } = this.ctx;
    this.T = timesOf(vo, audio, start, end);
    this.stage = new Stage(renderer, { fov: FOV, near: 0.01, far: 30, envIntensity: 0.22 });
    this.buildEditor();
    this.buildDock();
    this.buildLights();
    this.backdrop = new Backdrop([8, 5]);
    this.backdrop.mesh.position.set(0, -0.1, -1.6);
    this.stage.scene.add(this.backdrop.mesh);
    this.rig = new CameraRig(this.keys());
    this.warmUp();
  }

  // ---------------------------------------------------------------------------------------------- the editor

  /** A point on the editor (px from its top left, y down; z px out of its face), in the world. */
  private px(x: number, y: number, z = 0) {
    this.editG.updateMatrixWorld(true);
    return new THREE.Vector3((x - EDIT.w / 2) / 1000, (EDIT.h / 2 - y) / 1000, z / 1000).applyMatrix4(this.editG.matrixWorld);
  }

  private buildEditor() {
    this.edit = new Panel({ kind: 'editor', title: PATH, w: EDIT.w, h: EDIT.h, lang: 'md', gutter: 'numbers', size: SIZE, lines: fileLines(this.T) });
    this.editG.scale.setScalar(EDIT_SCALE);
    this.editG.add(this.edit.mesh);
    this.stage.scene.add(this.editG);
    // the caret: the Panel's bar (its width and height for this size), solid while it moves, blinking at rest
    const bone = new THREE.MeshBasicMaterial({ color: new THREE.Color().setRGB(...LIN.bone) });
    this.mats.push(bone);
    this.caret = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), bone);
    this.caret.scale.set(Math.max(2, 0.08 * SIZE) / 1000, (1.25 * SIZE) / 1000, 1);
    this.caret.renderOrder = 4;
    this.band = new Wash(EDIT);
    this.selection = new Wash(EDIT);
    this.flash = new Halo(EDIT, 'blood', 1);
    this.blade = new Blade(EDIT, BLADE.core, BLADE.halo);
    this.bladeConf = new Blade(EDIT, BLADE_SMALL.core, BLADE_SMALL.halo);
    this.signs = { old: new Bar(EDIT, 'blood'), neo: new Bar(EDIT, 'moss'), confOld: new Bar(EDIT, 'blood'), confNew: new Bar(EDIT, 'moss') };
    this.spot = new Spot(EDIT);
    this.aura = new Halo(EDIT, 'blood', 1);
    this.pen = new Halo(EDIT, 'moss', 13);
    this.editG.add(this.caret, this.band.mesh, this.selection.mesh, this.flash.mesh, this.blade.mesh, this.bladeConf.mesh, this.spot.mesh, this.aura.mesh, this.pen.mesh);
    for (const b of Object.values(this.signs)) this.editG.add(b.mesh);
  }

  /** Row i's top and its text's baseline (px) in the panel's layout at the file's time d (its rows open as they do). */
  private row(i: number, d: number) {
    return { top: this.edit.rowTop(i, d), base: this.edit.textOrigin(i, d).baseline };
  }

  /** The file's clock on the frame grid: what the Panel draws for the frame at t (one state across its shutter). */
  private docFrame(t: number) {
    return Math.round(docTime(frameIdx(t) / FPS, this.T) * FPS) / FPS;
  }

  private poseEditor(t: number) {
    const T = this.T, dq = this.docFrame(t), d = docTime(t, T);
    this.edit.draw(dq);
    // the panel takes the blow of the strike's impact: knocked back along its normal, ringing home
    const kt = t - T.strike.end;
    const kick = kt > 0 ? (Math.exp(-kt * 12) * Math.sin(kt * 2 * Math.PI * KICK.freq)) / 0.541 : 0;
    this.editG.position.z = (-KICK.px * EDIT_SCALE * kick) / 1000;

    // L15: the caret glides down the file to `Uses VS Code.` and lands on its downbeat with a small settle; the row's
    // band rides with it
    const live = t < T.strike.at + 0.02;
    const r0 = this.row(0, dq), r1 = this.row(ROW.old, dq);
    const glide = prog(t, T.change, T.land, ease.inOutCubic);
    const lt = t - T.land;
    const settle = lt > 0 ? 0.16 * Math.exp(-lt * LAND.decay) * Math.sin(lt * 2 * Math.PI * LAND.freq) : 0;
    const top = lerp(r0.top, r1.top, glide) + settle * G.lineH;
    const sel = prog(t, T.select, T.select + 0.14, ease.outCubic);
    const col = sel * len(VSCODE);
    this.caret.visible = live && t >= T.start;
    if (this.caret.visible) {
      // solid while it moves and as the selection runs, then blinking (16 frames on, 16 off) from where it came to rest
      const rest = T.select + 0.14;
      const on = t < rest || ((frameIdx(t) - frameIdx(rest)) % 32 + 32) % 32 < 16;
      this.caret.visible = on;
      const x = G.textX + col * G.adv, base = top + G.lineH / 2 + 0.365 * SIZE;
      this.caret.position.set((x + 1 - EDIT.w / 2) / 1000, (EDIT.h / 2 - (base - 0.355 * SIZE)) / 1000, 0.7 / 1000);
    }
    const bandOn = live ? prog(t, T.start, T.start + 0.1) : 0;
    this.band.set(0, top, EDIT.w, top + G.lineH, 0.007 * bandOn, 0.05 * bandOn);
    // the selection: runs across the line on "mind?", stirs on the beat after, and is taken by the blade as it cuts
    const cut = struckAt(d, T.strike, len(VSCODE));
    const stir = pulse(t, T.stir, 0.2);
    const selOn = sel > 0 && cut < len(VSCODE) && t < T.back.at;
    const sx0 = G.textX + cut * G.adv - 2, sx1 = G.textX + col * G.adv + 2;
    this.selection.set(sx0, r1.top + 5, sx1, r1.top + G.lineH - 5, selOn ? 0.05 + 0.05 * stir : 0);

    // the blade on `Uses VS Code.`: from the line's first character to the cut's edge, hot while it cuts (or runs back
    // out on a rewind), cooling to an ember that stays: the old line keeps its glow. The cut's impact flashes the row.
    const ro = this.row(ROW.old, dq), y = ro.base - 0.3 * SIZE;
    const heat = bladeHeat(d, T.strike);
    const rom = romance(t, T), breath = 0.5 - 0.5 * Math.cos(Math.max(0, t - T.fwd.end) * 2 * Math.PI * 0.75);
    // in the romance the cut softens to a faint line, and the words it struck take a faint blood light: a memory
    const ember = lerp(EMBER, 0.98 + 0.08 * breath, ease.inOutQuad(rom));
    this.blade.set(G.textX - 1, G.textX + cut * G.adv, y, heat, ember);
    const hit = d >= T.strike.end ? Math.exp(-(d - T.strike.end) / 0.07) : 0;
    const words = len(VSCODE) * G.adv;
    this.flash.set(G.textX + words / 2, y, 0.38 * hit, 1);
    this.flash.mesh.scale.set((words + 180) / 1000, 76 / 1000, 1);
    this.aura.set(G.textX + words / 2, ro.base - 0.35 * SIZE, (0.16 + 0.1 * breath) * ease.inOutQuad(rom), 1);
    this.aura.mesh.scale.set((words + 120) / 1000, 70 / 1000, 1);
    // the confidence's quick cut, a smaller blade that cools further
    const rc = this.row(ROW.confOld, dq), cutC = struckAt(d, T.conf, len(CONF_OLD));
    this.bladeConf.set(G.textX - 1, G.textX + cutC * G.adv, rc.base - 0.3 * SIZE, bladeHeat(d, T.conf, 0.25) * 0.8, 1.04, 2.6);
    // the diff's signs in the margin: blood beside each struck row from its first cut, moss beside each added row as it
    // opens; each flares on its event and settles to a glow that stays
    const rn = this.row(ROW.neo, dq), rcn = this.row(ROW.confNew, dq);
    const opened = (at: number) => clamp((dq - (at - 0.07)) / 0.07);
    const sign = (since: number) => SIGN.rest * (1 + 0.12 * rom) + (SIGN.flare - SIGN.rest) * Math.exp(-Math.max(0, since) / 0.25);
    const so = cut > 0 ? sign(d - T.strike.end) : 0, sc = cutC > 0 ? 0.8 * sign(d - T.conf.end) : 0;
    this.signs.old.set(SIGN_X, ro.top, ro.top + G.lineH, so);
    this.signs.confOld.set(SIGN_X, rc.top, rc.top + G.lineH, sc);
    this.signs.neo.set(SIGN_X, rn.top, rn.top + G.lineH, opened(T.add) * sign(d - T.add));
    this.signs.confNew.set(SIGN_X, rcn.top, rcn.top + G.lineH * opened(T.add), 0.8 * opened(T.add) * sign(d - T.add));
    // the added line is written in moss light: a small glow rides its typing head while it types (and as the playhead
    // brings it back), and goes out behind it
    const typed = this.edit.revealed(dq)[ROW.neo]!;
    const writing = dq >= T.add && dq <= T.addEnd + 0.12 ? 1 - clamp((dq - T.addEnd) / 0.12) : 0;
    this.pen.set(G.textX + typed * G.adv + 2, rn.base - 0.32 * SIZE, 1.25 * writing);
    // the romance's light: a warm pool on the two lines, the rest of the file falling into the dark
    this.spot.set(G.textX + 190, rn.top, 340, 92, ease.inOutQuad(rom));
  }

  // ---------------------------------------------------------------------------------------------- the dock

  private buildDock() {
    const front = new THREE.Vector3(0, 0, 1).applyQuaternion(this.editG.quaternion);
    this.dock = new Dock({ cmd: CMD, stat: STAT, commits: HISTORY }, EDIT, (x, y, z) => this.px(x, y, z), front, EDIT_SCALE / 1000);
    this.editG.add(this.dock.g);
    this.stage.scene.add(this.dock.thread.mesh);
    for (const b of this.dock.beads) this.stage.scene.add(b.mesh);
  }

  /** The playhead's x at history h (1: HEAD, 0: 8b21e04). */
  private headX(h: number) {
    return lerp(DOCK.commitX[OLD]!, DOCK.commitX[HEAD]!, h);
  }

  private poseDock(t: number) {
    const T = this.T, dk = this.dock;
    // it rises under the editor and lands on the downbeat (a firm spring), its type with it; the thread draws on across
    // it as it comes, and the beads pop onto their commits a 32nd note apart, HEAD last, all in place by the landing
    const rise = slam(t, T.dock, { freq: 4.4, damping: 0.68 });
    dk.g.visible = rise > 0;
    dk.g.position.y = (-(1 - rise) * 110) / 1000;
    // (in the romance it falls back into the dark with the rest of the room)
    const fade = clamp(rise * 1.4) * (1 - ease.inOutQuad(romance(t, T)));
    for (const k of ['prompt', 'key', 'cmd', 'stat', 'plus', 'minus', 'msg', 'hashOld', 'head'] as const) dk.mats[k].opacity = fade * (k === 'cmd' ? 0.9 : 1);
    // the stat types out on the downbeat
    const statN = Math.floor(clamp((t - T.dock + 0.01) * 420, 0, len(STAT)));
    for (const g of dk.stat.glyphs) g.mesh.visible = g.i < statN;
    const draw = prog(t, T.dock - 0.24, T.dock + 0.06, ease.outCubic);
    dk.thread.mesh.visible = draw > 0;
    dk.thread.setDraw(0, draw);
    dk.beads.forEach((b, i) => {
      const s = slam(t, T.dock - 0.12 + (i * T.beat) / 8, { freq: 5, damping: 0.6 });
      b.mesh.visible = s > 0.01;
      b.mesh.scale.setScalar(Math.max(1e-3, s));
    });
    // the playhead: on HEAD, then back and forth with the history; the hash it stands on comes up, the other recedes
    const h = historyAt(t, T);
    dk.setHead(this.headX(h));
    dk.head.visible = t > T.dock + 0.09 && fade > 0.01;
    const named = [[OLD, 1 - h], [HEAD, h]] as const;
    for (const [i, k] of named) dk.hashMats[i]!.opacity = fade * (0.45 + 0.55 * k);
    // the thread lights on meaning: moss as the stat lands and as the playhead brings the change back, blood as it runs
    // back through it to the old line; at rest it is bone
    const backK = t > T.back.at - 0.03 && t < T.fwd.at ? prog(t, T.back.at - 0.03, T.back.at + 0.08) * (1 - prog(t, T.back.end, T.back.end + 0.3, ease.outQuad)) : 0;
    const fwdK = Math.max(t > T.fwd.at - 0.03 && t < T.fwd.end ? prog(t, T.fwd.at - 0.03, T.fwd.at + 0.06) : 0, strandFlare(t, T.fwd.end, { lead: 0, decay: 0.6 }), strandFlare(t, T.dock, { lead: 0.03, decay: 0.5 }));
    const rest = DIFF_THREAD.rest, lit = DIFF_THREAD.glow;
    dk.thread.setStrandGlow({ blood: rest + (lit - rest) * clamp(backK), moss: rest + (lit - rest) * clamp(fwdK) });
  }

  // ---------------------------------------------------------------------------------------------- lights

  private buildLights() {
    const s = this.stage.scene;
    const c = this.px(EDIT.w * 0.45, EDIT.h + DOCK.threadY, DOCK.z);
    // neutral light only (lit bone stays out of the bloom's chroma gate): her's set for the thread and the beads, a key
    // from the upper left, a softbox in front of it, a hard rim from behind that sculpts the plies, and a kicker that
    // rings the bead the playhead stands on
    initAreaLights();
    const box = new THREE.RectAreaLight(0xffffff, 0.5, 1.2, 0.4);
    box.position.copy(c).add(new THREE.Vector3(-0.5, 0.55, 0.7));
    box.lookAt(c);
    const key = new THREE.DirectionalLight(0xffffff, 0.35);
    key.position.copy(c).add(new THREE.Vector3(-1.2, 1.6, 1.4));
    key.target.position.copy(c);
    const rim = new THREE.DirectionalLight(0xffffff, 4);
    rim.position.copy(c).add(new THREE.Vector3(1.0, 1.1, -1.6));
    rim.target.position.copy(c);
    this.kicker = new THREE.RectAreaLight(0xffffff, 0, 0.16, 0.16);
    s.add(box, key, key.target, rim, rim.target, this.kicker);
  }

  private poseLights(t: number) {
    const T = this.T, h = historyAt(t, T);
    const i = h < 0.5 ? OLD : HEAD, p = this.dock.places[i]!.pos;
    this.kicker.intensity = this.dock.g.visible ? 18 * (0.6 + 0.4 * Math.max(pulse(t, T.back.end, 0.25), pulse(t, T.fwd.end, 0.25), pulse(t, T.dock + 0.1, 0.3))) : 0;
    this.kicker.position.copy(p).add(new THREE.Vector3(0.05, 0.07, -0.12));
    this.kicker.lookAt(p);
    // the romance warms the studio: the pool behind the struck line comes up
    const r = romance(t, T), at = this.px(G.textX + 150, this.row(ROW.old, this.docFrame(t)).top);
    const eye = this.stage.camera.position, zb = this.backdrop.mesh.position.z;
    const behind = eye.clone().lerp(at, (zb - eye.z) / (at.z - eye.z));
    this.backdrop.set(behind.x - this.backdrop.mesh.position.x, behind.y - this.backdrop.mesh.position.y, 1.3, 0.75, 0.6 * ease.inOutQuad(r));
  }

  // ---------------------------------------------------------------------------------------------- the camera

  /** World points boxing editor px [x0, x1] × [y0, y1] (z px out of its face). */
  private box(x0: number, y0: number, x1: number, y1: number, z = 0) {
    return [this.px(x0, y0, z), this.px(x1, y0, z), this.px(x0, y1, z), this.px(x1, y1, z)];
  }

  private keys(): CamKey[] {
    const T = this.T, F = this.editG.matrixWorld, lh = G.lineH;
    this.editG.updateMatrixWorld(true);
    const top = (i: number, d: number) => this.row(i, d).top;
    const old = T.old, now = T.head + 1;
    const x1 = G.textX + len(VSCODE) * G.adv, xn = G.textX + len(NEOVIM) * G.adv;
    const dockLow = EDIT.h + DOCK.threadY + DOCK.msgY + 10;
    const H0 = this.headX(1), H1 = this.headX(0);
    return [
      // the cut: the top of the file, close, the caret on line 1 under the title bar
      fitKey(T.start, this.box(0, 0, 600, top(6, old)), { az: -25, el: 8, fov: FOV, margin: [0.1, 0.12], bias: [-0.04, 0], roll: -2 }, F),
      // craning down the file with the caret, landing with it on `Uses VS Code.`
      fitKey(T.land + 0.12, this.box(0, top(3, old), 600, top(ROW.old, old) + 2.2 * lh), { az: -22, el: 5, fov: FOV, margin: [0.1, 0.12], bias: [-0.04, 0.02], roll: -1.6 }, F, ease.inOutCubic),
      // a slow push toward the line through "mind?"
      fitKey(T.strike.at - 0.05, this.box(10, top(7, old), 540, top(ROW.old, old) + 2.6 * lh), { az: -19, el: 3, fov: FOV, margin: [0.08, 0.07], bias: [-0.02, 0], roll: -1.3 }, F, ease.inOutQuad),
      // the blade cuts: the camera drives in with it and the blow lands, the line just under the frame's middle
      fitKey(T.strike.end + 0.06, this.box(G.textX - 70, top(8, old) + 0.3 * lh, x1 + 230, top(ROW.old, old) + 2.6 * lh), { az: -18, el: 3, fov: FOV, margin: [0.07, 0.07], bias: [-0.02, -0.02], roll: -1.1 }, F, ease.inQuad),
      // and takes the blow, easing back as the two new rows open: both changes in frame, the new line typing in
      fitKey(T.add + 0.2, this.box(G.textX - 60, top(3, now), xn + 40, top(ROW.neo, now) + 1.4 * lh), { az: -17, el: 4, fov: FOV, margin: [0.08, 0.09], bias: [0, 0.04], roll: -1 }, F, ease.inOutCubic),
      // drifting along it as it types
      fitKey(T.dock - 0.22, this.box(G.textX - 40, top(3, now), xn + 60, top(ROW.neo, now) + 1.4 * lh), { az: -16, el: 4, fov: FOV, margin: [0.08, 0.09], bias: [0, 0.04], roll: -1 }, F, ease.inOutQuad),
      // the dock lands under the editor on the downbeat: the camera whips down onto it, holding the two lines above
      fitKey(T.dock + 0.02, this.box(0, top(ROW.old, now) - 1.3 * lh, EDIT.w + 10, dockLow + 6, DOCK.z / 2), { az: -14.5, el: 7, fov: FOV, margin: [0.065, 0.065], bias: [0, 0], roll: -1.1 }, F, ease.inOutCubic),
      fitKey(T.well, this.box(0, top(ROW.old, now) - 1.2 * lh, EDIT.w + 10, dockLow, DOCK.z / 2), { az: -14, el: 7, fov: FOV, margin: [0.07, 0.07], bias: [0, 0], roll: -1 }, F, ease.outQuad),
      // L17, slowly in all the while: leaning toward 8b21e04 as the playhead runs back to it, home again with it, and on in
      // to the two lines as the dock sinks out of the bottom of the frame
      fitKey(T.back.end + 0.06, this.box(-20, top(ROW.old, now) - 1.0 * lh, EDIT.w + 5, dockLow - 10, DOCK.z / 2), { az: -13, el: 6.5, fov: FOV, margin: [0.07, 0.07], bias: [0.05 * (H0 - H1) / 220, 0], roll: -0.9 }, F, ease.inOutQuad),
      fitKey(T.fwd.at + 0.1, this.box(10, top(ROW.old, now) - 0.9 * lh, EDIT.w + 10, EDIT.h + DOCK.threadY + 28, DOCK.z / 2), { az: -12, el: 5.5, fov: FOV, margin: [0.06, 0.05], bias: [0, -0.02], roll: -0.85 }, F, ease.inOutQuad),
      // the romance: in close on the two lines, the old one's ember, coming round and down a little
      fitKey(T.end, this.box(G.textX - 70, top(11, now) - 0.1 * lh, xn + 20, top(ROW.neo, now) + 1.5 * lh), { az: -21, el: 2, fov: FOV, margin: [0.05, 0.12], bias: [0.03, -0.02], roll: -1.4 }, F, (u: number) => 0.5 - 0.5 * Math.cos(Math.PI * u)),
    ];
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
    this.rig.apply(st.camera, T.fwd.end);
    this.poseEditor(T.strike.end + 0.05);
    this.poseDock(T.fwd.end);
    for (const m of [this.blade.mesh, this.bladeConf.mesh, this.caret, this.band.mesh, this.selection.mesh, this.flash.mesh, this.spot.mesh, this.aura.mesh, this.pen.mesh, ...Object.values(this.signs).map((b) => b.mesh)]) m.visible = true;
    st.compile();
    st.render(rt, { dof: { focus: 0.4, fstop: 4 } });
    for (const o of culled) o.frustumCulled = true;
    rt.dispose();
  }

  render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides {
    const t = f.t, T = this.T, st = this.stage;
    this.rig.apply(st.camera, t);
    this.poseEditor(t);
    this.poseDock(t);
    this.poseLights(t);

    const r = this.ctx.renderer, cc = r.getClearColor(new THREE.Color()), ca = r.getClearAlpha();
    r.setClearColor(INK, 1); // what the glass sees through the transmission pass
    st.render(out, { dof: this.focus(t) });
    r.setClearColor(cc, ca);

    // the blow jolts the frame; the dock's landing and the playhead's arrivals punch in a hair; the scrub's speed strains
    // the lens (its fringes open as the playhead runs); the romance warms the glow's halation and closes the vignette
    const dt = t - T.strike.end;
    const shake = dt >= 0 ? 3.2 * Math.exp(-dt * 16) * Math.cos(dt * 2 * Math.PI * 9) : 0;
    const zoom = 0.006 * pulse(t, T.strike.end, 0.1) + 0.004 * pulse(t, T.dock, 0.12) + 0.003 * pulse(t, T.back.end, 0.12) + 0.004 * pulse(t, T.fwd.end, 0.14);
    const speed = Math.abs(historyAt(t + 0.01, T) - historyAt(t - 0.01, T)) / 0.02;
    const rom = romance(t, T);
    return {
      shake: [0, shake], zoom: 1 + zoom, ca: LOOK.ca * (1 + 0.9 * clamp(speed / 4)),
      halation: LOOK.halation + 0.3 * rom, bloom: LOOK.bloom + 0.15 * rom, vignette: LOOK.vignette + 0.12 * rom,
    };
  }

  /** Focus as a ring turns (diopters): the caret, the line, the typing head, the two lines and the dock, the ember. */
  private focus(t: number) {
    const T = this.T, st = this.stage;
    const inv = (p: THREE.Vector3) => 1 / Math.max(0.03, st.depthOf(p));
    const dq = this.docFrame(t);
    const at = (x: number, i: number, z = 0) => inv(this.px(x, this.row(i, dq).base - 0.35 * SIZE, z));
    const head = G.textX + clamp((t - T.add) / (T.addEnd - T.add)) * len(NEOVIM) * G.adv;
    const ks: [number, number, ((x: number) => number)?][] = [
      [T.start, at(G.textX + 60, 0)],
      [T.land + 0.05, at(G.textX + 90, ROW.old), ease.inOutCubic],
      [T.strike.at, at(G.textX + 90, ROW.old)],
      [T.strike.end, at(G.textX + len(VSCODE) * G.adv, ROW.old), ease.inOutQuad],
      [T.add, at(G.textX + len(VSCODE) * G.adv, ROW.old)],
      [T.addEnd, at(head, ROW.neo), ease.inOutQuad],
      [T.dock + 0.1, at(G.textX + 200, ROW.neo, DOCK.z / 3), ease.inOutCubic],
      [T.fwd.end, at(G.textX + 150, ROW.old)],
      [T.end, at(G.textX + len(VSCODE) * G.adv, ROW.old), ease.inOutQuad],
    ];
    const rom = romance(t, T);
    const fstop = t < T.dock - 0.1 ? 2.8 : lerp(4, 2, ease.inOutQuad(rom));
    return { focus: 1 / keys(t, ks), fstop };
  }

  override dispose() {
    const r = this.ctx.renderer;
    if (this.dock?.beads[0]) freeTransmission(r, this.dock.beads[0].material);
    this.edit?.dispose();
    this.caret?.geometry.dispose();
    for (const x of [this.band, this.selection, this.flash, this.blade, this.bladeConf, this.spot, this.aura, this.pen, this.backdrop]) x?.dispose();
    if (this.signs) for (const b of Object.values(this.signs)) b.dispose();
    this.dock?.dispose();
    for (const m of this.mats) m.dispose();
    this.stage?.dispose();
  }
}
