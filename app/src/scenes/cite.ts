// Scene 07 `cite`: "Ask me why I believe something... I'll show you the line." (Plan 2 Task 17; spec §4 07.) Every
// answer cites its source, and the source is a line of a file you can open: provenance as a thread sewn from the claim
// into the file.
//
// One world and one camera, every time from the data (her measured onsets, the score's beats; cite-time.ts):
// 1. The question. An agent chat hangs in close 3D, the memory file below and behind it. `what editor do I use?` is
//    typing in its bubble as the cut lands, the camera in close on it; it slides down and across the conversation as the
//    answer `neovim.` streams in on the downbeat she starts "Ask" on.
// 2. Why. A `why?` chip pops in after the answer; the pointer glides to it and clicks on "why", the chip pressing in,
//    and lets go on the beat: the citation label springs open out of the chip and streams in, `facts/people/user.md#editor
//    · L11–14 · 3f9a1c2`, and the file below jumps to its lines on the next beat.
// 3. The thread. As the citation lands the diff thread is drawn out of the label's end, falling in a long S in front of
//    the file, the camera craning down with its tip, a little moss light running down inside it. It comes to hang over
//    line 11 in the file's right margin through "something…" and her pause.
// 4. The needle. On "I'll" the thread's tip stiffens into a needle, the change running back from the point to the eye
//    (cite-needle.ts), moss light in its point. It draws back a hair and strikes into the file on the downbeat, the camera
//    driving in with it; behind the panel it runs in slow motion under lines 11–14, its light showing through the panel as
//    it passes and each line lighting moss in its wake; it bursts out under line 14 on the eighth and pulls through, past
//    the panel's edge.
// 5. The line. On "line." the pull lands: the thread snaps taut from the citation into the file and rings, moss light
//    floods up it from the stitch to the label, the four lines flare, `L11–14` lights in the label, and the blame gutter
//    slides out of the file beside them, `3f9a1c2 · 2026-07-26`, as the camera pulls back to all of it: the claim, the
//    thread, the source.
import * as THREE from 'three';
import { Scene, type Frame, type PostOverrides } from '../engine/scene';
import { CameraRig, Stage, initAreaLights, type CamKey } from '../engine/stage';
import { W, H, makeRT } from '../engine/gl';
import { Panel, panelLayout, type PanelLine, type PanelMark } from '../engine/panels';
import { DIFF_THREAD, Thread, envelopeOf, strandFlare, strandGlow, type StrandGlow } from '../engine/thread3d';
import { Bar, Halo } from '../engine/panel-light';
import { LIN } from '../engine/palette';
import { LOOK } from '../engine/look';
import { slam, spring } from '../engine/motion';
import { clamp, ease, keys, lerp, noise1, prog, pulse, smoothstep } from '../engine/util';
import { Backdrop, fitKey } from './diff-fx';
import { EYE_TO_TIP, eyeAt, formAt, tautAt, threadEnd, timesOf, tipAt, tipPasses, type Run, type Times } from './cite-time';
import { ArcPath, airRoute, stitchRoute, type P3 } from './cite-path';
import { Needle } from './cite-needle';
import { Chip, Pointer } from './cite-ui';
import S from './cite.strings.json';

// ------------------------------------------------------------------------------------------------ the copy

const [PATH, DASH, TIER, TAGS, CONF, UPDATED, DARK, SHIPS, EDITOR, NEOVIM, TZ, IST, WORKS, ASK, ANSWER, WHY, CITE, BLAME] =
  S as string[] as [string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string];
const len = (s: string) => Array.from(s).length;

/** The file at 3f9a1c2, spec §11.4, its 18 lines: the citation's lines 11–14 are rows 10–13. */
export const FILE_TEXT = [DASH, TIER, TAGS, CONF, UPDATED, DASH, '', DARK, SHIPS, '', EDITOR, '', NEOVIM, '', TZ, '', IST, WORKS];
export const CITED = [10, 11, 12, 13] as const;

/** The citation's runs (code points): the path, the section, the line range, the commit; and the dots between. */
const at = (s: string) => CITE.indexOf(s);
export const CITE_RUNS = {
  path: [0, len(PATH)] as const,
  section: [len(PATH), at(' ·')] as const,
  range: [at('L11'), at('L11') + len('L11–14')] as const,
  hash: [len(CITE) - 7, len(CITE)] as const,
};

// ------------------------------------------------------------------------------------------------ the layout (px)

/** Code size of the file and the chat, and the world's scale: world units per px (repo's and diff's file: 0.4 mm a px). */
const SIZE = 24;
const PXW = 0.4 / 1000;
/** The editor: repo's file (640 wide, 24 px code), in an eight-row viewport that jumps to the cited section when the
 * citation lands, as following its link would: `## Editor` (line 11) to the top, the file's end at the foot. */
const EW = 640, ROWS = 8, SCROLL = 10;
const EG = panelLayout({ kind: 'editor', size: SIZE, gutter: 'numbers', lines: FILE_TEXT.map(() => ({})) });
const EH = EG.bar + EG.padTop + ROWS * EG.lineH + EG.padBottom;
/** A row's top in the editor once it has jumped (px). */
const rowTop = (i: number) => EG.bar + EG.padTop + (i - SCROLL) * EG.lineH;
/** The rows the stitch binds: the top of line 11 and the foot of line 14; its x just past their longest line. */
const TOP = rowTop(CITED[0]), FOOT = rowTop(CITED[3]) + EG.lineH;
const STITCH_X = 520;
/** The chat: the question, a gap, the answer; just wide enough for the question's bubble. */
const CW = 440;
const CG = panelLayout({ kind: 'chat', size: SIZE, lines: [{ kind: 'cmd' }, {}, { kind: 'out' }] });
const CH = CG.bar + CG.padTop + 3 * CG.lineH + CG.padBottom;
/** A chat row's top (px). */
const chatRow = (i: number) => CG.bar + CG.padTop + i * CG.lineH;
/** The chip: after the answer on its row, its size and its label's em (px). */
const CHIP = { gap: 18, w: 70, h: 30, em: 17 };
/**
 * The citation label: a card that opens out of the chip, hanging under the answer and over the chat's foot, a little in
 * front of it (chat px: its top left, its depth), set in mono at 22 px. The thread comes out of its face at its right end.
 */
const LABEL_SIZE = 22;
const LG = panelLayout({ kind: 'card', size: LABEL_SIZE, lines: [{}] });
const LABEL = { x: 10, y: chatRow(3) - 6, z: 18, w: Math.ceil(2 * LG.padX + len(CITE) * LG.adv), h: LG.padTop + LG.lineH + LG.padBottom };
/** Where the thread comes out of the label (label px): just after the citation's last character, mid-row. */
const LABEL_HEAD = { x: LG.padX + len(CITE) * LG.adv + 11, y: LG.padTop + LG.lineH / 2 };
/**
 * The chat's top left in the editor's px, and its depth (px, in front of the file's face, so the thread falls from the
 * label through the air in front of the file all the way to the stitch): placed so the thread drops just about straight
 * down from the label's end into the margin, the label's foot 46 px above the file.
 */
const CHAT: P3 = [STITCH_X + 6 - (LABEL.x + LABEL_HEAD.x), -46 - (LABEL.y + LABEL.h), 60];
/** The blame gutter: a tab that slides out of the file's left edge beside the cited lines (its code size, width, and how
 * far it stays tucked behind the file). */
const TAB = { size: 20, w: 320, tuck: 30 };
const TG = panelLayout({ kind: 'card', size: TAB.size, lines: [{}] });
/** Its top: its text's baseline on line 11's. */
const TAB_TOP = TOP + EG.lineH / 2 + 0.365 * SIZE - (TG.padTop + TG.lineH / 2 + 0.365 * TAB.size);
const TAB_H = FOOT + 9 - TAB_TOP;

// ------------------------------------------------------------------------------------------------ the world

/** The lens: repo's and diff's short tele. */
const FOV = 24;
/** The thread's radius (px): diff's dock thread, a hair finer, as a sewing thread is. */
const THREAD_PX = 3;
/** The needle's moss: its point while it sews, at rest after; the forming front's ring. */
const TIP = { sew: 2.6, rest: 1.05, ring: 3.4 };

const INK = new THREE.Color().setRGB(...LIN.ink);

type Sew = { path: ArcPath; run: Run; tip: number; tipLevel: number };

export default class Cite extends Scene {
  private T!: Times;
  private stage!: Stage;
  private rig!: CameraRig;
  private edG = new THREE.Group();
  private chatG = new THREE.Group();
  private labelG = new THREE.Group();
  private tabG = new THREE.Group();
  private edit!: Panel;
  private chat!: Panel;
  private label!: Panel;
  private tab!: Panel;
  private chip!: Chip;
  private pointer!: Pointer;
  private thread!: Thread;
  private needle!: Needle;
  /** The route's fixed part, from A (behind the panel, out through B, to the rest). */
  private stitch!: P3[];
  /** Where the thread comes out of the label (editor px). */
  private from!: P3;
  /** The route as last set on the thread (its key), and its measure. */
  private routeKey = '';
  private path!: ArcPath;
  /** Light on the panels: the needle's point seen through the file, the holes' flashes, the four lines' flare, the
   * citation's range, the blame gutter's sign. */
  private through!: Halo;
  private flashA!: Halo;
  private flashB!: Halo;
  private flare!: Halo;
  private rangeGlow!: Halo;
  private sign!: Bar;
  private backdrop!: Backdrop;
  private kicker!: THREE.RectAreaLight;

  override init() {
    const { renderer, vo, audio, start, end } = this.ctx;
    this.T = timesOf(vo, audio, start, end);
    this.stage = new Stage(renderer, { fov: FOV, near: 0.01, far: 30, envIntensity: 0.22 });
    this.edG.scale.setScalar(PXW * 1000);
    this.chatG.scale.setScalar(PXW * 1000);
    this.stage.scene.add(this.edG, this.chatG);
    this.chatG.position.copy(this.edPx(CHAT[0] + CW / 2, CHAT[1] + CH / 2, CHAT[2]));
    this.buildChat();
    this.buildThread();
    this.buildEditor();
    this.buildTab();
    this.buildLights();
    this.backdrop = new Backdrop([8, 5]);
    this.backdrop.mesh.position.copy(this.edPx(EW / 2, 120, -2400));
    this.stage.scene.add(this.backdrop.mesh);
    this.rig = new CameraRig(this.keys());
    this.warmUp();
  }

  // ---------------------------------------------------------------------------------------------- places

  /** A point in the editor's px (x right, y down from its top edge, z out of its face), in the world. */
  private edPx(x: number, y: number, z = 0) {
    this.edG.updateMatrixWorld(true);
    return new THREE.Vector3((x - EW / 2) / 1000, (EH / 2 - y) / 1000, z / 1000).applyMatrix4(this.edG.matrixWorld);
  }

  /** A point in the chat's px, in the editor's px. */
  private static chatToEd(x: number, y: number, z = 0): P3 {
    return [CHAT[0] + x, CHAT[1] + y, CHAT[2] + z];
  }

  /** A point in the chat's px, in the world. */
  private chatPx(x: number, y: number, z = 0) {
    return this.edPx(...Cite.chatToEd(x, y, z));
  }

  /** Local position in a panel's group for its px (x, y, z): the panel's mesh is centred on the group. */
  private static local(w: number, h: number, x: number, y: number, z = 0) {
    return new THREE.Vector3((x - w / 2) / 1000, (h / 2 - y) / 1000, z / 1000);
  }

  // ---------------------------------------------------------------------------------------------- the chat

  private buildChat() {
    const T = this.T, R = CITE_RUNS;
    this.chat = new Panel({
      kind: 'chat', w: CW, h: CH, size: SIZE, opaque: true,
      lines: [
        { text: ASK, kind: 'cmd', at: T.question.at, cps: (len(ASK) - 1) / (T.question.end - T.question.at) },
        { text: '' },
        { text: ANSWER, kind: 'out', at: T.answer - 0.01, cps: (len(ANSWER) - 1) / (T.answerEnd - T.answer + 0.01) },
      ],
    });
    this.chatG.add(this.chat.mesh);
    // the chip after the answer, the pointer over the chat
    this.chip = new Chip(WHY, CHIP.w, CHIP.h, CHIP.em);
    this.pointer = new Pointer(1.1);
    this.chatG.add(this.chip.g, this.pointer.g);
    // the citation label: streams in once it has opened; its range lights moss when the stitch lands
    this.label = new Panel({
      kind: 'card', w: LABEL.w, h: LABEL.h, size: LABEL_SIZE,
      lines: [{
        text: CITE, kind: 'out', at: T.cite.at, cps: (len(CITE) - 1) / (T.cite.end - T.cite.at),
        // the path recedes, its section and the line range stand forward, the dots between are faint, the commit is a number
        spans: [
          { from: R.path[0], to: R.path[1], tone: 'str' },
          { from: R.section[0], to: R.section[1], tone: 'kw' },
          { from: R.section[1], to: R.range[0], tone: 'punc' },
          { from: R.range[0], to: R.range[1], tone: 'kw' },
          { from: R.range[1], to: R.hash[0], tone: 'punc' },
          { from: R.hash[0], to: R.hash[1], tone: 'num' },
        ],
        highlight: { from: R.range[0] - 0.25, to: R.range[1] + 0.25, tone: 'moss', alpha: 0.16, at: T.pull + 0.1, fade: 0.1 },
      }],
    });
    this.rangeGlow = new Halo({ w: LABEL.w, h: LABEL.h }, 'moss', 1);
    this.labelG.add(this.label.mesh, this.rangeGlow.mesh);
    this.chatG.add(this.labelG);
  }

  /** The chip's centre (chat px). */
  private static chipAt() {
    return { x: CG.textX + len(ANSWER) * CG.adv + CHIP.gap + CHIP.w / 2, y: chatRow(2) + CG.lineH / 2 };
  }

  private poseChat(t: number) {
    const T = this.T;
    this.chat.draw(t);
    // the chip: pops in as the answer completes; lifts as the pointer comes to it; presses in on the click and lets go on
    // the beat, staying lit after (its question is open)
    const pop = clamp((t - T.chip) / 0.07);
    const s = t < T.chip ? 0 : 0.86 + 0.14 * spring(t - T.chip);
    const hover = prog(t, T.click - 0.16, T.click - 0.02, ease.outQuad);
    const press = t >= T.click && t < T.release ? 1 - Math.exp(-(t - T.click) / 0.025) : 0;
    const ring = t >= T.release ? Math.exp(-(t - T.release) / 0.06) * Math.sin((t - T.release) * 2 * Math.PI * 9) * 0.04 : 0;
    const c = Cite.chipAt();
    this.chip.g.position.copy(Cite.local(CW, CH, c.x, c.y + 1.5 * press, 3 - 3 * press));
    this.chip.g.scale.setScalar(Math.max(1e-3, s * (1 - 0.06 * press + ring)));
    const lit = t >= T.release ? 0.09 : 0;
    this.chip.set(pop, 0.04 * hover + 0.12 * press + lit, Math.max(hover, t >= T.click ? 1 : 0));
    // the pointer: glides in from below and to the right once the chip is there, settles on it, clicks, and drifts off
    const glide = prog(t, T.chip - 0.05, T.click - 0.05, ease.inOutCubic);
    const leave = prog(t, T.release + 0.06, T.release + 0.45, ease.inQuad);
    const x = lerp(c.x + 200, c.x - 6, glide) + 60 * leave, y = lerp(c.y + 90, c.y + 4, glide) + 70 * leave;
    const curve = Math.sin(Math.PI * glide) * 24; // an arc, not a line: a hand's path
    this.pointer.g.position.copy(Cite.local(CW, CH, x + curve * 0.4, y - curve, 12 - 4 * press));
    this.pointer.g.scale.setScalar(1 - 0.12 * press);
    this.pointer.set(prog(t, T.chip - 0.05, T.chip + 0.1) * (1 - leave));
    // the label: opens out of the chip on the release, a firm spring, and the citation streams into it
    const open = t < T.release ? 0 : spring(t - T.release, 4.6, 0.68);
    const home = Cite.local(CW, CH, LABEL.x + LABEL.w / 2, LABEL.y + LABEL.h / 2, LABEL.z);
    const from = Cite.local(CW, CH, c.x, c.y, LABEL.z);
    this.labelG.visible = open > 0.002;
    this.labelG.position.copy(from.lerp(home, open));
    this.labelG.scale.set(Math.max(1e-3, 0.12 + 0.88 * open), Math.max(1e-3, 0.3 + 0.7 * open), 1);
    this.label.opacity = clamp((t - T.release) / 0.06);
    this.label.draw(t);
    // the citation's range glows with the stitch's light once it has run up the thread
    const R = CITE_RUNS.range, o = this.label.cellOrigin(0, (R[0] + R[1]) / 2);
    const g = 0.5 * strandFlare(t, T.pull + 0.12, { lead: 0.06, decay: 0.7 }) + (t > T.pull + 0.12 ? 0.1 : 0);
    this.rangeGlow.set(o.x, o.baseline - 0.33 * LABEL_SIZE, g, 1);
    this.rangeGlow.mesh.scale.set(((R[1] - R[0]) * LG.adv + 60) / 1000, 40 / 1000, 1);
  }

  // ---------------------------------------------------------------------------------------------- the thread

  /** The route at t (editor px): the air from the label's end to A, slack or taut, swaying while it hangs; then the stitch. */
  private routeAt(t: number): P3[] {
    const T = this.T;
    const live = smoothstep(T.draw.at, T.draw.at + 0.4, t) * (1 - smoothstep(T.form.at - 0.3, T.form.at, t));
    const sway: P3 = live > 0 ? [7 * live * noise1(t * 1.1, 3), 2 * live * noise1(t * 0.8, 7), 6 * live * noise1(t * 0.9, 11)] : [0, 0, 0];
    return [...airRoute(this.from, this.stitch[0]!, tautAt(t, T), sway), ...this.stitch.slice(1)];
  }

  /** How many points the air route has (A is its last). */
  private static readonly AIR = airRoute([0, 0, 0], [0, 1, 0], 0).length;

  /** Where the run's holes and end are along a route's measure. */
  private static runOf(path: ArcPath): Run {
    return { a: path.atPoint(Cite.AIR - 1), b: path.atPoint(Cite.AIR + 3), end: path.length };
  }

  private buildThread() {
    this.from = Cite.chatToEd(LABEL.x + LABEL_HEAD.x, LABEL.y + LABEL_HEAD.y, LABEL.z - 3);
    this.stitch = stitchRoute({ x: STITCH_X, top: TOP, foot: FOOT });
    const route = this.routeAt(this.T.start);
    this.path = new ArcPath(route);
    this.routeKey = JSON.stringify(route);
    this.thread = new Thread(route.map((p) => this.edPx(...p)), { ...DIFF_THREAD, radius: THREAD_PX * PXW, fuzz: 0.5 });
    this.thread.setStrandLight({}); // the strip's program, compiled in the warm-up
    this.thread.setDraw(0, 0);
    this.stage.scene.add(this.thread.mesh);
    this.needle = new Needle(PXW);
    this.stage.scene.add(this.needle.mesh);
  }

  private poseThread(t: number): Sew {
    const T = this.T, route = this.routeAt(t), key = JSON.stringify(route);
    if (key !== this.routeKey) {
      this.routeKey = key;
      this.path = new ArcPath(route);
      this.thread.setPoints(route.map((p) => this.edPx(...p)));
    }
    const path = this.path, L = path.length, run = Cite.runOf(path);
    const tip = tipAt(t, T, run), end = threadEnd(t, T, run), k = formAt(t, T);
    this.thread.setDraw(0, clamp(end / L));
    // the moss light: down inside the thread behind its tip as it is drawn out; in the eye while the needle sews; then the
    // pull's flood, from the stitch up to the label, and the strand lit after it
    const glows: StrandGlow[] = [];
    if (t > T.draw.at && t < T.form.end) glows.push({ u: (tip - 24) / L, w: 28 / L, k: 0.42 * prog(t, T.draw.at, T.draw.at + 0.2) });
    if (k > 0 && t < T.pull + 0.25) glows.push({ u: eyeAt(tip) / L, w: 34 / L, k: 0.8 * (1 - prog(t, T.pull, T.pull + 0.25)) });
    if (t > T.pull - 0.04) {
      const r = prog(t, T.pull - 0.04, T.pull + 0.16, ease.outCubic);
      glows.push({ u: lerp(run.a / L, 0, r), w: 0.16, k: 1 - 0.35 * r });
    }
    this.thread.setStrandLight({ moss: envelopeOf(glows) });
    this.thread.setStrandGlow({ moss: strandGlow(t, T.pull, { lead: 0.02, decay: 1.6 }) });

    // the needle: once its tip has stiffened, its eye on the thread's end and its point down the route
    const eye = path.at(eyeAt(tip)).pos, point = path.at(tip).pos;
    const we = this.edPx(eye.x, eye.y, eye.z), wp = this.edPx(point.x, point.y, point.z);
    const sewing = t >= T.form.end;
    const tipLevel = k <= 0 ? 0 : !sewing ? TIP.sew * smoothstep(0.5, 1, k) : t < T.pull ? TIP.sew : lerp(TIP.sew, TIP.rest, prog(t, T.pull, T.pull + 0.4, ease.outQuad));
    const ring = TIP.ring * Math.sin(Math.PI * k);
    this.needle.set(we, wp.clone().sub(we), this.stage.camera.position.clone().sub(we), k, tipLevel, ring);
    return { path, run, tip, tipLevel };
  }

  // ---------------------------------------------------------------------------------------------- the file

  private buildEditor() {
    const T = this.T;
    // each cited line lights moss as the needle's point passes under it, and flares with the pull
    const path = new ArcPath(this.routeAt(T.strike));
    const run = Cite.runOf(path);
    const lines: PanelLine[] = FILE_TEXT.map((text, i) => {
      if (!(CITED as readonly number[]).includes(i)) return { text };
      const s = path.crossing(1, rowTop(i) + EG.lineH / 2, run.a, run.b);
      const lit = tipPasses(Number.isNaN(s) ? run.a : s, T, run);
      const marks: PanelMark[] = [
        { tone: 'moss', alpha: 0.1, at: lit - 0.02, fade: 0.09 },
        { tone: 'moss', alpha: 0.07, at: T.pull - 0.02, until: T.pull + 0.5, fade: 0.08 },
      ];
      return { text, highlight: marks };
    });
    this.edit = new Panel({
      kind: 'editor', title: PATH, w: EW, rows: ROWS, lang: 'md', gutter: 'numbers', size: SIZE, opaque: true, lines,
      // the file jumps to the cited section on the beat after the citation lands: line 11 to the viewport's top
      scroll: (tq) => SCROLL * ease.inOutCubic(prog(tq, T.scroll - 0.3, T.scroll)),
    });
    this.edG.add(this.edit.mesh);
    const dims = { w: EW, h: EH };
    this.through = new Halo(dims, 'moss', 16);
    this.flashA = new Halo(dims, 'moss', 15);
    this.flashB = new Halo(dims, 'moss', 14);
    this.flare = new Halo(dims, 'moss', 1);
    this.edG.add(this.through.mesh, this.flashA.mesh, this.flashB.mesh, this.flare.mesh);
  }

  private poseEditor(t: number, sew: Sew) {
    const T = this.T;
    this.edit.draw(t);
    // the needle's point seen through the panel while it runs behind it: a soft moss light, wider and fainter the deeper
    const p = sew.path.at(sew.tip).pos;
    const behind = p.z < -0.5 && sew.tip > sew.run.a && sew.tip < sew.run.b + 2;
    this.through.set(p.x, p.y, behind ? 0.42 * (sew.tipLevel / TIP.sew) * Math.exp(p.z / 30) : 0, 13 + 0.3 * Math.abs(p.z));
    // the holes flash as the point goes in and comes out
    const A = this.stitch[0]!, B = this.stitch[4]!;
    this.flashA.set(A[0], A[1], t >= T.strike ? 1.1 * Math.exp(-(t - T.strike) / 0.05) : 0, 15);
    this.flashB.set(B[0], B[1], t >= T.exit ? 0.9 * Math.exp(-(t - T.exit) / 0.05) : 0, 14);
    // the four lines flare with the pull
    const f = strandFlare(t, T.pull, { lead: 0.03, decay: 0.55 });
    this.flare.set(EW / 2 - 20, (TOP + FOOT) / 2, 0.09 * f, 1);
    this.flare.mesh.scale.set((EW + 320) / 1000, (FOOT - TOP + 90) / 1000, 1);
  }

  // ---------------------------------------------------------------------------------------------- the blame gutter

  private buildTab() {
    this.tab = new Panel({
      kind: 'card', w: TAB.w, h: TAB_H, size: TAB.size, opaque: true,
      lines: [{ text: BLAME, spans: [{ from: 0, to: 7, tone: 'kw' }, { from: 7, to: 10, tone: 'punc' }, { from: 10, to: len(BLAME), tone: 'str' }] }],
    });
    this.sign = new Bar({ w: TAB.w, h: TAB_H }, 'moss');
    this.tabG.add(this.tab.mesh, this.sign.mesh);
    this.edG.add(this.tabG);
    this.tab.draw(this.T.start);
  }

  /** The tab: tucked behind the file, it slides out on the pull to stand beside the lines, its sign lit. */
  private poseTab(t: number) {
    const T = this.T;
    const hidden = 10, out = TAB.tuck - TAB.w;
    // a firm spring that lands just after the pull, overshooting a hair and settling home
    const x = lerp(hidden, out, slam(t, T.pull + 0.04, { freq: 4.5, damping: 0.66 }));
    this.tabG.visible = t >= T.pull - 0.1;
    this.tabG.position.copy(Cite.local(EW, EH, x + TAB.w / 2, TAB_TOP + TAB_H / 2, -6));
    this.tab.draw(t);
    // its sign: a moss bar beside the file's edge over the cited rows, lit as it lands and glowing after
    const y0 = TOP - TAB_TOP + 3, y1 = FOOT - TAB_TOP - 3;
    this.sign.set(TAB.w - TAB.tuck - 11, y0, y1, t < T.pull ? 0 : 1.3 + 1.2 * Math.exp(-(t - T.pull) / 0.25));
  }

  // ---------------------------------------------------------------------------------------------- lights

  private buildLights() {
    const s = this.stage.scene, c = this.edPx(STITCH_X - 120, (TOP + FOOT) / 2 - 80, 30);
    // neutral light only (lit bone stays out of the bloom's chroma gate): diff's set, a key from the upper left, a softbox
    // in front of it, a hard rim from behind that sculpts the plies and edges the needle, and a kicker that rides the needle
    initAreaLights();
    const box = new THREE.RectAreaLight(0xffffff, 0.55, 1.2, 0.4);
    box.position.copy(c).add(new THREE.Vector3(-0.5, 0.55, 0.7));
    box.lookAt(c);
    const key = new THREE.DirectionalLight(0xffffff, 0.35);
    key.position.copy(c).add(new THREE.Vector3(-1.2, 1.6, 1.4));
    key.target.position.copy(c);
    const rim = new THREE.DirectionalLight(0xffffff, 4);
    rim.position.copy(c).add(new THREE.Vector3(1.0, 1.1, -1.6));
    rim.target.position.copy(c);
    this.kicker = new THREE.RectAreaLight(0xffffff, 0, 0.12, 0.12);
    s.add(box, key, key.target, rim, rim.target, this.kicker);
  }

  private poseLights(t: number, sew: Sew) {
    const T = this.T;
    // the kicker rides above the needle from its forming to its rest, ringing it on the strike and the pull; through the
    // forming and the strike it slides from its head to its point, a highlight running down the glaze
    const slide = prog(t, T.form.at, T.strike + 0.06, ease.inOutQuad) * (1 - prog(t, T.exit, T.pull, ease.inOutQuad));
    const p = sew.path.at(sew.tip - EYE_TO_TIP * (0.95 - 0.8 * slide)).pos, w = this.edPx(p.x, p.y, p.z);
    const on = t > T.form.at - 0.05;
    this.kicker.intensity = on ? 9 * (0.55 + 0.45 * Math.max(pulse(t, T.strike, 0.12), pulse(t, T.pull, 0.2), pulse(t, T.form.end, 0.1))) : 0;
    this.kicker.position.copy(w).add(new THREE.Vector3(-0.03, 0.05, 0.07));
    this.kicker.lookAt(w);
    // the wall behind lifts a little behind the lines once they are lit (the pool where the camera sees them against it)
    const r = prog(t, T.pull - 0.05, T.end, ease.outQuad);
    const at = this.edPx(320, (TOP + FOOT) / 2), eye = this.stage.camera.position, b = this.backdrop.mesh.position;
    const behind = eye.clone().lerp(at, (b.z - eye.z) / (at.z - eye.z));
    this.backdrop.set(behind.x - b.x, behind.y - b.y, 1.0, 0.6, 0.3 * r);
  }

  // ---------------------------------------------------------------------------------------------- the camera

  /** World points boxing editor px [x0, x1] × [y0, y1] at depth z (px). */
  private box(x0: number, y0: number, x1: number, y1: number, z = 0) {
    return [this.edPx(x0, y0, z), this.edPx(x1, y0, z), this.edPx(x0, y1, z), this.edPx(x1, y1, z)];
  }

  /** The same for a box in the chat's px (on its face, or `z` in front of it). */
  private chatBox(x0: number, y0: number, x1: number, y1: number, z = 0) {
    return [this.chatPx(x0, y0, z), this.chatPx(x1, y0, z), this.chatPx(x0, y1, z), this.chatPx(x1, y1, z)];
  }

  /** The label's box (chat px), and how far past its foot. */
  private labelBox(x0 = LABEL.x, x1 = LABEL.x + LABEL.w, below = 0) {
    return this.chatBox(x0, LABEL.y, x1, LABEL.y + LABEL.h + below, LABEL.z);
  }

  private keys(): CamKey[] {
    const T = this.T, F = this.edG.matrixWorld, r = chatRow;
    this.edG.updateMatrixWorld(true);
    const c = Cite.chipAt();
    return [
      // the question: in close on its bubble as it types, the rest of the chat falling away to the left
      fitKey(T.start, this.chatBox(56, r(0) - 16, CW, r(1) + 22), { az: -22, el: 2, fov: FOV, margin: [0.08, 0.16], bias: [0.02, 0.02], roll: -1.6 }, F),
      // sliding left and down along the conversation as the answer streams in on the downbeat
      fitKey(T.answer + 0.05, this.chatBox(0, r(0) - 12, CW, r(3) + 6), { az: -17, el: 3, fov: FOV, margin: [0.06, 0.1], bias: [0, 0.02], roll: -1.3 }, F, ease.inOutQuad),
      // on in to the answer and its chip for the click
      fitKey(T.click, this.chatBox(0, r(2) - 30, c.x + 120, r(3) + 34), { az: -14, el: 4, fov: FOV, margin: [0.08, 0.14], bias: [-0.02, 0.02], roll: -1.1 }, F, ease.inOutCubic),
      // back out with the label as it opens and the citation streams into it
      fitKey(T.cite.end, [...this.chatBox(0, r(2) - 16, CW, r(3)), ...this.labelBox(LABEL.x, LABEL.x + LABEL.w, 12)], { az: -12, el: 5, fov: FOV, margin: [0.05, 0.14], bias: [0, 0.02], roll: -1 }, F, ease.inOutQuad),
      // the thread drawn out: the camera cranes down with its tip from the label's end toward the file
      fitKey(T.draw.at + 0.5, [...this.labelBox(LABEL.x + LABEL.w / 2), ...this.box(260, -30, EW + 70, TOP + 40)], { az: -12, el: 7, fov: FOV, margin: [0.06, 0.07], bias: [0, 0], roll: -1 }, F, ease.inOutCubic),
      // the tip comes to hang over line 11 by the lines' ends: the file, the thread falling to it from the label
      fitKey(T.draw.end, [...this.labelBox(LABEL.x + LABEL.w - 220), ...this.box(40, -20, EW + 60, FOOT + 40)], { az: -15, el: 8, fov: FOV, margin: [0.05, 0.06], bias: [0, 0], roll: -1.1 }, F, ease.inOutQuad),
      // the pause: in on the hanging thread over the lines' ends as its tip turns into a needle, the whole of it in frame
      fitKey(T.form.at, this.box(250, -110, EW + 50, FOOT - 20), { az: -19, el: 10, fov: FOV, margin: [0.05, 0.06], bias: [0, 0], roll: -1.3 }, F, ease.inOutQuad),
      // the strike: the camera drives in with it and round, close on the needle going into the lines
      fitKey(T.strike + 0.07, this.box(320, -80, EW + 30, FOOT - 50), { az: -25, el: 12, fov: FOV, margin: [0.05, 0.05], bias: [0, 0], roll: -1.6 }, F, ease.inQuad),
      // through the slow motion under the lines, easing back to hold both holes as the point comes out of the second
      fitKey(T.exit, this.box(230, -40, EW + 70, FOOT + 60), { az: -23, el: 10, fov: FOV, margin: [0.05, 0.05], bias: [0, 0], roll: -1.4 }, F, ease.inOutQuad),
      // the pull: back out to all of it, the question and its claim, the citation, the thread, the lines it was sewn
      // through, the blame beside them (inside the title-safe frame)
      fitKey(T.pull + 0.16, [...this.chatBox(0, r(0) - 10, CW, r(3)), ...this.labelBox(), ...this.box(TAB.tuck - TAB.w - 12, TOP - 10, EW + 180, EH + 4)], { az: -13, el: 6, fov: FOV, margin: [0.07, 0.075], bias: [0, 0], roll: -0.9 }, F, ease.inOutCubic),
      fitKey(T.end, [...this.chatBox(10, r(0) - 4, CW, r(3)), ...this.labelBox(LABEL.x + 10, LABEL.x + LABEL.w - 10), ...this.box(TAB.tuck - TAB.w - 4, TOP, EW + 170, EH - 6)], { az: -12, el: 5.5, fov: FOV, margin: [0.07, 0.075], bias: [0, 0], roll: -0.8 }, F, ease.outQuad),
    ];
  }

  /** Focus as a focus ring turns (diopters): the question, the answer, the chip, the citation, the thread's tip, the holes, the lines. */
  private focus(t: number, sew: Sew) {
    const T = this.T, st = this.stage, r = chatRow, lh = CG.lineH;
    const D = (p: THREE.Vector3) => 1 / Math.max(0.03, st.depthOf(p));
    const tipP = () => {
      const p = sew.path.at(sew.tip).pos;
      return D(this.edPx(p.x, p.y, p.z));
    };
    const c = Cite.chipAt(), R = CITE_RUNS.range;
    const stops: [number, () => number, ((x: number) => number)?][] = [
      [T.start, () => D(this.chatPx(CW - 150, r(0) + lh / 2))],
      [T.answer - 0.1, () => D(this.chatPx(CW - 150, r(0) + lh / 2))],
      [T.answer + 0.1, () => D(this.chatPx(70, r(2) + lh / 2)), ease.inOutQuad],
      [T.click - 0.05, () => D(this.chatPx(c.x, c.y)), ease.inOutQuad],
      [T.cite.end - 0.1, () => D(this.chatPx(LABEL.x + LG.padX + R[0] * LG.adv, LABEL.y + LABEL_HEAD.y, LABEL.z)), ease.inOutQuad],
      [T.draw.at + 0.3, tipP, ease.inOutQuad],
      [T.draw.end, tipP],
      [T.form.end, () => D(this.edPx(STITCH_X, TOP + 10)), ease.inOutQuad],
      [T.exit, () => D(this.edPx(STITCH_X, FOOT)), ease.inOutQuad],
      [T.pull + 0.14, () => D(this.edPx(300, (TOP + FOOT) / 2)), ease.inOutCubic],
    ];
    let d = stops[0]![1]();
    for (let i = 0; i < stops.length; i++) {
      const [ti, fi, e] = stops[i]!;
      if (t < ti) {
        if (i > 0) {
          const [tp, fp] = stops[i - 1]!;
          d = lerp(fp(), fi(), (e ?? ease.linear)(clamp((t - tp) / (ti - tp))));
        }
        break;
      }
      d = fi();
    }
    const fstop = keys(t, [[T.start, 2.8], [T.cite.end, 3.2], [T.form.at, 3.4], [T.strike, 3.2], [T.exit, 3.4], [T.pull + 0.16, 5.6, ease.inOutCubic]]);
    return { focus: 1 / d, fstop };
  }

  // ---------------------------------------------------------------------------------------------- render

  /**
   * Draw everything once before the first frame: shaders compile for the stage's target, and textures and geometry
   * upload. Nothing it sets outlives it: render() sets all state from t.
   */
  private warmUp() {
    const st = this.stage, rt = makeRT(W, H), T = this.T;
    const culled: THREE.Object3D[] = [];
    st.scene.traverse((o) => {
      if (o.frustumCulled) (o.frustumCulled = false), culled.push(o);
    });
    this.rig.apply(st.camera, T.exit);
    this.poseChat(T.end);
    const sew = this.poseThread(T.form.end + 0.05);
    this.poseEditor(T.exit + 0.01, sew);
    this.poseTab(T.end);
    this.poseLights(T.strike, sew);
    for (const m of [this.through.mesh, this.flashA.mesh, this.flashB.mesh, this.flare.mesh, this.rangeGlow.mesh, this.sign.mesh, this.needle.mesh]) m.visible = true;
    this.tabG.visible = this.chip.g.visible = this.pointer.g.visible = this.labelG.visible = true;
    st.compile();
    st.render(rt, { dof: { focus: 0.5, fstop: 4 } });
    for (const o of culled) o.frustumCulled = true;
    rt.dispose();
  }

  render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides {
    const t = f.t, T = this.T, st = this.stage;
    this.rig.apply(st.camera, t);
    this.poseChat(t);
    const sew = this.poseThread(t);
    this.poseEditor(t, sew);
    this.poseTab(t);
    this.poseLights(t, sew);

    const r = this.ctx.renderer, cc = r.getClearColor(new THREE.Color()), ca = r.getClearAlpha();
    r.setClearColor(INK, 1);
    st.render(out, { dof: this.focus(t, sew) });
    r.setClearColor(cc, ca);

    // the strike jolts the frame and the pull lands with a punch; the lens strains as the needle runs; the glow opens a
    // little with the lines' light
    const ds = t - T.strike, dp = t - T.pull;
    const shake = (ds >= 0 ? 2.6 * Math.exp(-ds * 18) * Math.cos(ds * 2 * Math.PI * 10) : 0) + (dp >= 0 ? 1.6 * Math.exp(-dp * 16) * Math.cos(dp * 2 * Math.PI * 8) : 0);
    const zoom = 0.003 * pulse(t, T.answer, 0.1) + 0.003 * pulse(t, T.click, 0.08) + 0.007 * pulse(t, T.strike, 0.09) + 0.004 * pulse(t, T.exit, 0.08) + 0.008 * pulse(t, T.pull, 0.12);
    const strain = Math.max(pulse(t, T.strike, 0.1), 0.7 * pulse(t, T.exit, 0.1), 0.6 * prog(t, T.exit, T.pull) * (1 - prog(t, T.pull, T.pull + 0.1)));
    const glowUp = strandFlare(t, T.pull, { lead: 0.03, decay: 0.8 });
    return {
      shake: [0, shake], zoom: 1 + zoom, ca: LOOK.ca * (1 + 0.9 * strain),
      bloom: LOOK.bloom + 0.12 * glowUp, halation: LOOK.halation + 0.1 * glowUp,
    };
  }

  override dispose() {
    this.edit?.dispose();
    this.chat?.dispose();
    this.label?.dispose();
    this.tab?.dispose();
    this.chip?.dispose();
    this.pointer?.dispose();
    for (const x of [this.through, this.flashA, this.flashB, this.flare, this.rangeGlow, this.sign, this.backdrop]) x?.dispose();
    this.thread?.dispose();
    this.needle?.dispose();
    this.stage?.dispose();
  }
}
