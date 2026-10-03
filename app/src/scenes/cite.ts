// Scene 07 `cite`: "Ask me why I believe something... I'll show you the line." (Plan 2 Task 17; spec §4 07.) Every
// answer cites its source, and the source is a line of a file you can open: provenance as one thread laid from the
// citation onto the lines it cites.
//
// One world and one camera, every time from the data (her measured onsets, the score's beats; cite-time.ts):
// 1. The question. An agent chat hangs in close 3D, the memory file below and behind it. `what editor do I use?` is
//    typing in its bubble as the cut lands, the camera in close on it; it slides down and across the conversation as the
//    answer `neovim.` streams in on the downbeat she starts "Ask" on.
// 2. Why. A `why?` chip pops in after the answer; the pointer glides to it and clicks on "why", the chip pressing in,
//    and lets go on the beat: the citation label springs open out of the chip and streams in, `facts/people/user.md#editor
//    · L11–14 · 3f9a1c2`, and the file below jumps to its lines on the next beat.
// 3. The thread. As the citation lands a fine diff thread is drawn out under `L11–14`: it lies on the label's face as
//    an underline, runs off the label's foot and falls in one long curve through the air in front of the file, a little
//    moss light running inside it behind its tip, the camera following the tip down in one move. It never stops: it
//    drifts through her pause, coming down onto the file just past the lines' ends.
// 4. The seam. On the downbeat ("I'll") it lands on the file's face at the top of line 11 and lies down the margin
//    beside lines 11–14, a seam a hair above the face (cite-path.ts), turning in under line 14 like a bracket's foot;
//    each line lights moss as the tip passes it, the light spreading under it like ink.
// 5. The line. On "line." the light lands: the air draws in and rings, moss light floods up the thread from the seam to
//    the underline, the four lines flare, `L11–14` lights in the label, and the blame gutter slides out of the file
//    beside them, `3f9a1c2 · 2026-07-26`, as the camera pulls back to all of it: the claim, the thread, the source.
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
import { layEnd, tautAt, timesOf, tipAt, tipPasses, type Run, type Times } from './cite-time';
import { ArcPath, LAND, seamRoute, type P3, type SeamSpec } from './cite-path';
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
/** The rows the seam runs beside: the top of line 11 and the foot of line 14; its x just past their longest line. */
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
/** The label's right end, past the citation's last character, mid-row (label px): the chat is placed by it. */
const LABEL_HEAD = { x: LG.padX + len(CITE) * LG.adv + 11, y: LG.padTop + LG.lineH / 2 };
/** The underline under `L11–14` (label px): how far below the baseline, how far past the range either side. */
const UNDER = { drop: 7, pad: 2 };
/**
 * The chat's top left in the editor's px, and its depth (px, in front of the file's face, so the thread falls from the
 * label through the air in front of the file all the way to the seam): placed so the label's right end stands over the
 * margin, the label's foot 80 px above the file.
 */
const CHAT: P3 = [STITCH_X + 6 - (LABEL.x + LABEL_HEAD.x), -80 - (LABEL.y + LABEL.h), 60];
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
/** The thread's radius (px): a fine thread, a stroke of the type's weight, so it sits in the UI's scale. */
const THREAD_PX = 1.8;
/** The send-off's run down the seam before the cut (s). */
const SEND_OFF = 0.22;
/** How far above a face the thread's axis lies where it lies on one (px): its radius and a little air. */
const LIFT = THREAD_PX + 1.3;

const INK = new THREE.Color().setRGB(...LIN.ink);

type Sew = { path: ArcPath; run: Run; tip: number };

/** A point in the chat's px, in the editor's px. */
const chatToEd = (x: number, y: number, z = 0): P3 => [CHAT[0] + x, CHAT[1] + y, CHAT[2] + z];

/** The label's and the file's faces (editor px): x0, y0, x1, y1 and the face's z. */
export const FACES = {
  label: { x0: CHAT[0] + LABEL.x, y0: CHAT[1] + LABEL.y, x1: CHAT[0] + LABEL.x + LABEL.w, y1: CHAT[1] + LABEL.y + LABEL.h, z: CHAT[2] + LABEL.z },
  file: { x0: 0, y0: 0, x1: EW, y1: EH, z: 0 },
};
export { THREAD_PX };

/**
 * Where the thread lies (editor px): the underline under the citation's range on the label's face (the range's cells on
 * the label's mono grid, its baseline as the Panel sets it), the label's foot, and the seam beside the cited rows.
 */
export function seamSpec(): SeamSpec {
  const R = CITE_RUNS.range, base = LG.bar + LG.padTop + LG.lineH / 2 + 0.365 * LABEL_SIZE;
  const y = LABEL.y + base + UNDER.drop;
  const [x0, uy, uz] = chatToEd(LABEL.x + LG.textX + R[0] * LG.adv - UNDER.pad, y, LABEL.z);
  const x1 = chatToEd(LABEL.x + LG.textX + R[1] * LG.adv + UNDER.pad, y)[0];
  return { under: { x0, x1, y: uy, z: uz }, labelFoot: FACES.label.y1, x: STITCH_X, top: TOP, foot: FOOT, lift: LIFT };
}

// ------------------------------------------------------------------------------------------------ the last stop (pure)

/** The file's frame in the world: it hangs at the origin, PXW world units a px, facing +z (Cite.init sets edG so). */
const ED_FRAME = new THREE.Matrix4().makeScale(PXW * 1000, PXW * 1000, PXW * 1000);
/** A point in the editor's px (x right, y down from its top edge, z out of its face), in the world (as Cite.edPx). */
const edAt = (x: number, y: number, z = 0) => new THREE.Vector3((x - EW / 2) / 1000, (EH / 2 - y) / 1000, z / 1000).applyMatrix4(ED_FRAME);
/** World points boxing editor px [x0, x1] × [y0, y1] at depth z (px). */
const boxAt = (x0: number, y0: number, x1: number, y1: number, z = 0) => [edAt(x0, y0, z), edAt(x1, y0, z), edAt(x0, y1, z), edAt(x1, y1, z)];
/** The same for a box in the chat's px (on its face, or `z` in front of it), as Cite.chatBox. */
const chatBoxAt = (x0: number, y0: number, x1: number, y1: number, z = 0) => [[x0, y0], [x1, y0], [x0, y1], [x1, y1]].map(([x, y]) => edAt(...chatToEd(x!, y!, z)));

/**
 * The camera's last stop, as the scene ends on all of it: the question and its claim, the citation, the thread, the lines
 * it lies beside, the blame beside them (inside the title-safe frame).
 */
function restKey(t: number): CamKey {
  const label = chatBoxAt(LABEL.x, LABEL.y, LABEL.x + LABEL.w, LABEL.y + LABEL.h, LABEL.z);
  return fitKey(t, [...chatBoxAt(0, chatRow(0) - 8, CW, chatRow(3)), ...label, ...boxAt(TAB.tuck - TAB.w - 10, TOP - 6, EW + 175, EH)], { az: -12.5, el: 5.8, fov: FOV, margin: [0.07, 0.095], bias: [0, -0.02], roll: -0.85 }, ED_FRAME);
}

/**
 * The seam's run in the frame as the scene ends (cite → braid whips out along it): the unit direction, logical px with
 * y down, from where it lies down onto line 11 to its foot beside line 14, through the camera's last stop.
 */
export function seamAxis(): [number, number] {
  const cam = new THREE.PerspectiveCamera(FOV, W / H, 0.01, 30);
  new CameraRig([restKey(0)]).apply(cam, 0);
  const px = (p: THREE.Vector3) => { const v = p.clone().project(cam); return [((v.x + 1) / 2) * W, ((1 - v.y) / 2) * H] as const; };
  const a = px(edAt(STITCH_X, TOP, LIFT)), b = px(edAt(STITCH_X, FOOT, LIFT));
  const d = Math.hypot(b[0] - a[0], b[1] - a[1]);
  return [(b[0] - a[0]) / d, (b[1] - a[1]) / d];
}

/** An ease 0..1 that leaves at speed a and arrives at speed b (multiples of the segment's mean speed): a cubic Hermite. */
const hermiteEase = (a: number, b: number) => (u: number) => {
  const u2 = u * u, u3 = u2 * u;
  return (u3 - 2 * u2 + u) * a + (-2 * u3 + 3 * u2) + (u3 - u2) * b;
};

/**
 * Keys `move` after the stop `from`, as one move: the camera leaves `from` and stops on the last key, passing the keys
 * between at speed. Each inner key's speed is the mean of the segments either side of it (the camera's travel per s),
 * and each segment's ease leaves and arrives at those speeds, so the speed is continuous through the keys.
 */
function glide(from: CamKey, move: CamKey[]): CamKey[] {
  const all = [from, ...move];
  const d = (i: number) => Math.hypot(...all[i + 1]!.pos.map((v, j) => v - all[i]!.pos[j]!)) + Math.hypot(...all[i + 1]!.target.map((v, j) => v - all[i]!.target[j]!));
  const mean = (i: number) => d(i) / (all[i + 1]!.t - all[i]!.t);
  // the speed at each key: 0 at the ends, the mean of its segments' mean speeds between
  const v = all.map((_, i) => (i === 0 || i === all.length - 1 ? 0 : (mean(i - 1) + mean(i)) / 2));
  return move.map((k, j) => {
    const m = mean(j);
    const a = m > 0 ? Math.min(2.5, v[j]! / m) : 0, b = m > 0 ? Math.min(2.5, v[j + 1]! / m) : 0;
    return { ...k, ease: hermiteEase(a, b) };
  });
}

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
  /** Where the thread lies: the underline, the label's foot, the seam (editor px). */
  private seam!: SeamSpec;
  /** The route as last set on the thread (its key), and its measure. */
  private routeKey = '';
  private path!: ArcPath;
  /** Light on the panels: the ink under the seam's tip as it lays, the landing's bloom, the four lines' flare, the
   * citation's range, the blame gutter's sign. */
  private ink!: Halo;
  private bloom!: Halo;
  private flare!: Halo;
  private rangeGlow!: Halo;
  private sign!: Bar;
  private backdrop!: Backdrop;

  override init() {
    const { renderer, vo, audio, start, end } = this.ctx;
    this.T = timesOf(vo, audio, start, end);
    this.stage = new Stage(renderer, { fov: FOV, near: 0.01, far: 30, envIntensity: 0.22 });
    this.edG.scale.setScalar(PXW * 1000);
    this.edG.updateMatrixWorld(true); // the file's frame, fixed from here on: edPx reads it
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
    return new THREE.Vector3((x - EW / 2) / 1000, (EH / 2 - y) / 1000, z / 1000).applyMatrix4(this.edG.matrixWorld);
  }

  /** A point in the chat's px, in the editor's px. */
  private static chatToEd(x: number, y: number, z = 0): P3 {
    return chatToEd(x, y, z);
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
    // the citation label: streams in once it has opened; its range lights moss when the light lands
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
    // the citation's range glows with the seam's light once it has run up the thread
    const R = CITE_RUNS.range, o = this.label.cellOrigin(0, (R[0] + R[1]) / 2);
    const g = 0.5 * strandFlare(t, T.pull + 0.12, { lead: 0.06, decay: 0.7 }) + (t > T.pull + 0.12 ? 0.1 : 0);
    this.rangeGlow.set(o.x, o.baseline - 0.33 * LABEL_SIZE, g, 1);
    this.rangeGlow.mesh.scale.set(((R[1] - R[0]) * LG.adv + 60) / 1000, 40 / 1000, 1);
  }

  // ---------------------------------------------------------------------------------------------- the thread

  /** The route at t (editor px): the underline, the air (slack, breathing while it is drawn, drawn in on the pull), the seam. */
  private routeAt(t: number): P3[] {
    const T = this.T;
    // the air breathes while the thread is drawn and is still by the landing, so the seam lies down from a steady line
    const live = smoothstep(T.draw.at, T.draw.at + 0.4, t) * (1 - smoothstep(T.form.at, T.strike, t));
    const sway: P3 = live > 0 ? [6 * live * noise1(t * 1.1, 3), 4 * live * noise1(t * 0.8, 7), 5 * live * noise1(t * 0.9, 11)] : [0, 0, 0];
    return seamRoute(this.seam, tautAt(t, T), sway);
  }

  /** Where the thread lands on the file and where it ends, along a route's measure. */
  private static runOf(path: ArcPath): Run {
    return { land: path.atPoint(LAND), end: path.length };
  }

  private buildThread() {
    this.seam = seamSpec();
    const R = CITE_RUNS.range, o = this.label.cellOrigin(0, R[0]);
    if (Math.abs(LABEL.x + o.x - UNDER.pad - (this.seam.under.x0 - CHAT[0])) > 0.01) throw new Error('cite: the underline is off the label\'s range');
    const route = this.routeAt(this.T.start);
    this.path = new ArcPath(route);
    this.routeKey = JSON.stringify(route);
    this.thread = new Thread(route.map((p) => this.edPx(...p)), { ...DIFF_THREAD, radius: THREAD_PX * PXW, fuzz: 0.3 });
    this.thread.setStrandLight({}); // the strip's program, compiled in the warm-up
    this.thread.setDraw(0, 0);
    this.stage.scene.add(this.thread.mesh);
  }

  private poseThread(t: number): Sew {
    const T = this.T, route = this.routeAt(t), key = JSON.stringify(route);
    if (key !== this.routeKey) {
      this.routeKey = key;
      this.path = new ArcPath(route);
      this.thread.setPoints(route.map((p) => this.edPx(...p)));
    }
    const path = this.path, L = path.length, run = Cite.runOf(path);
    const tip = tipAt(t, T, run);
    this.thread.setDraw(0, clamp(tip / L));
    // the moss light: inside the thread behind its tip as it is drawn and lays the seam; the seam keeps a little of it
    // once laid (the ink settled); then the pull's flood, from the seam's foot up to the underline, and the strand lit after
    const glows: StrandGlow[] = [];
    const laid = layEnd(T);
    if (t > T.draw.at && t < laid + 0.3) glows.push({ u: (tip - 26) / L, w: 34 / L, k: 0.75 * prog(t, T.draw.at, T.draw.at + 0.2) * (1 - prog(t, laid, laid + 0.3)) });
    if (t > T.strike) glows.push({ u: (run.land + run.end) / 2 / L, w: (0.5 * (run.end - run.land)) / L, k: 0.3 * prog(t, T.strike, laid + 0.2, ease.inOutQuad) });
    if (t > T.pull - 0.04) {
      const r = prog(t, T.pull - 0.04, T.pull + 0.16, ease.outCubic);
      glows.push({ u: lerp(1, 0, r), w: 0.16, k: 1 - 0.35 * r });
    }
    // the send-off: as the scene ends a light runs down the seam from the landing to its foot and on out of it, faster
    // and faster, and the camera whips after it (cite → braid, along the seam: seamAxis)
    const go = prog(t, T.end - SEND_OFF, T.end, ease.inQuad);
    if (go > 0) glows.push({ u: lerp(run.land / L, 1.05, go), w: 0.06, k: 0.9 * clamp(go * 5) });
    this.thread.setStrandLight({ moss: envelopeOf(glows) });
    this.thread.setStrandGlow({ moss: strandGlow(t, T.pull, { lead: 0.02, decay: 1.6 }) });
    return { path, run, tip };
  }

  // ---------------------------------------------------------------------------------------------- the file

  private buildEditor() {
    const T = this.T;
    // each cited line lights moss as the seam's tip passes it, spreading in like ink, and flares with the pull
    const path = new ArcPath(this.routeAt(T.strike));
    const run = Cite.runOf(path);
    const lines: PanelLine[] = FILE_TEXT.map((text, i) => {
      if (!(CITED as readonly number[]).includes(i)) return { text };
      const s = path.crossing(1, rowTop(i) + EG.lineH / 2, run.land, run.end);
      const lit = tipPasses(Number.isNaN(s) ? run.land : s, T, run);
      const marks: PanelMark[] = [
        { tone: 'moss', alpha: 0.1, at: lit - 0.04, fade: 0.16 },
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
    this.ink = new Halo(dims, 'moss', 22);
    this.bloom = new Halo(dims, 'moss', 34);
    this.flare = new Halo(dims, 'moss', 1);
    this.edG.add(this.ink.mesh, this.bloom.mesh, this.flare.mesh);
  }

  private poseEditor(t: number, sew: Sew) {
    const T = this.T;
    this.edit.draw(t);
    // the ink: a soft moss light on the face under the seam's tip while it lays, fading as it comes to rest
    const p = sew.path.at(sew.tip).pos, laid = layEnd(T);
    const laying = t >= T.strike ? 0.1 * prog(t, T.strike, T.strike + 0.08) * (1 - prog(t, laid - 0.05, laid + 0.25)) : 0;
    // and the send-off's light runs down the seam to its foot on the face beside it, the camera whipping after it
    const go = prog(t, T.end - SEND_OFF, T.end, ease.inQuad);
    const q = go > 0 ? sew.path.at(lerp(sew.run.land, sew.run.end, go)).pos : p;
    this.ink.set(q.x, q.y, Math.max(laying, 0.3 * clamp(go * 5)), 30);
    // the landing: a slow bloom where the thread touches the file, spreading and fading
    const A = this.seam, dl = t - T.strike;
    this.bloom.set(A.x, A.top + 6, dl >= 0 ? 0.1 * smoothstep(0, 0.05, dl) * Math.exp(-dl / 0.3) : 0, 40 + 50 * clamp(dl / 0.5));
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
    // in front of it, and a hard rim from behind that draws the fine thread's edge against the dark
    initAreaLights();
    const box = new THREE.RectAreaLight(0xffffff, 1.0, 1.2, 0.4);
    box.position.copy(c).add(new THREE.Vector3(-0.5, 0.55, 0.7));
    box.lookAt(c);
    const key = new THREE.DirectionalLight(0xffffff, 0.6);
    key.position.copy(c).add(new THREE.Vector3(-1.2, 1.6, 1.4));
    key.target.position.copy(c);
    const rim = new THREE.DirectionalLight(0xffffff, 4);
    rim.position.copy(c).add(new THREE.Vector3(1.0, 1.1, -1.6));
    rim.target.position.copy(c);
    s.add(box, key, key.target, rim, rim.target);
  }

  private poseLights(t: number) {
    const T = this.T;
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
    const c = Cite.chipAt();
    const ks: CamKey[] = [
      // the question: in close on its bubble as it types, the rest of the chat falling away to the left
      fitKey(T.start, this.chatBox(56, r(0) - 16, CW, r(1) + 22), { az: -22, el: 2, fov: FOV, margin: [0.08, 0.16], bias: [0.02, 0.02], roll: -1.6 }, F),
      // sliding left and down along the conversation as the answer streams in on the downbeat
      fitKey(T.answer + 0.05, this.chatBox(0, r(0) - 12, CW, r(3) + 6), { az: -17, el: 3, fov: FOV, margin: [0.06, 0.1], bias: [0, 0.02], roll: -1.3 }, F, ease.inOutQuad),
      // on in to the answer and its chip for the click
      fitKey(T.click, this.chatBox(0, r(2) - 30, c.x + 120, r(3) + 34), { az: -14, el: 4, fov: FOV, margin: [0.08, 0.14], bias: [-0.02, 0.02], roll: -1.1 }, F, ease.inOutCubic),
      // back out with the label as it opens and the citation streams into it
      fitKey(T.cite.end, [...this.chatBox(0, r(2) - 16, CW, r(3)), ...this.labelBox(LABEL.x, LABEL.x + LABEL.w, 12)], { az: -12, el: 5, fov: FOV, margin: [0.05, 0.14], bias: [0, 0.02], roll: -1 }, F, ease.inOutQuad),
    ];
    // From the citation to the end, one move that never stops: down with the thread's tip as it falls, through its
    // landing, a drift along the seam as it lays, and the pull back on "line." to all of it. The keys between are passed
    // through at speed (glide matches the camera's speed either side of each), so only the citation and the end are stops.
    const under = this.seam.under, ux = (x: number) => x - CHAT[0];
    const move: CamKey[] = [
      // the landing: the thread's whole fall from the underline to the top of line 11, the lines below it
      fitKey(T.strike, [...this.labelBox(ux(under.x0) - 30, LABEL.x + LABEL.w), ...this.box(230, -40, EW + 60, FOOT + 30)], { az: -16, el: 8, fov: FOV, margin: [0.06, 0.07], bias: [0, 0], roll: -1.2 }, F),
      // the light lands: the seam laid, the thread from the underline down to it, a little closer and round
      fitKey(T.pull, [...this.labelBox(ux(under.x0) - 20, LABEL.x + LABEL.w), ...this.box(150, -20, EW + 50, FOOT + 24)], { az: -18, el: 8.5, fov: FOV, margin: [0.06, 0.07], bias: [0, 0], roll: -1.3 }, F),
      // settling as the scene ends on all of it: the question and its claim, the citation, the thread, the lines it lies
      // beside, the blame beside them (inside the title-safe frame)
      restKey(T.end - 0.02),
    ];
    return [...ks, ...glide(ks[ks.length - 1]!, move)];
  }

  /** Focus as a focus ring turns (diopters): the question, the answer, the chip, the citation, the thread's tip, the lines. */
  private focus(t: number, sew: Sew) {
    const T = this.T, st = this.stage, r = chatRow, lh = CG.lineH;
    const D = (p: THREE.Vector3) => 1 / Math.max(0.03, st.depthOf(p));
    const tipP = () => {
      const p = sew.path.at(sew.tip).pos;
      return D(this.edPx(p.x, p.y, p.z));
    };
    const c = Cite.chipAt(), R = CITE_RUNS.range;
    // the question's typing head, then where it ended
    const head = () => {
      const o = this.chat.cellOrigin(0, this.chat.revealed(t)[0]!, t);
      return D(this.chatPx(o.x, o.baseline - 0.35 * SIZE));
    };
    const stops: [number, () => number, ((x: number) => number)?][] = [
      [T.start, head],
      [T.answer - 0.1, head],
      [T.answer + 0.1, () => D(this.chatPx(70, r(2) + lh / 2)), ease.inOutQuad],
      [T.click - 0.05, () => D(this.chatPx(c.x, c.y)), ease.inOutQuad],
      [T.cite.end - 0.1, () => D(this.chatPx(LABEL.x + LG.padX + R[0] * LG.adv, LABEL.y + LABEL_HEAD.y, LABEL.z)), ease.inOutQuad],
      [T.draw.at + 0.3, tipP, ease.inOutQuad],
      [layEnd(T), tipP],
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
    const fstop = keys(t, [[T.start, 2.8], [T.cite.end, 3.2], [T.strike, 4], [T.pull + 0.16, 5.6, ease.inOutCubic]]);
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
    const sew = this.poseThread(T.exit);
    this.poseEditor(T.exit, sew);
    this.poseTab(T.end);
    this.poseLights(T.strike);
    for (const m of [this.ink.mesh, this.bloom.mesh, this.flare.mesh, this.rangeGlow.mesh, this.sign.mesh]) m.visible = true;
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
    this.poseLights(t);

    const r = this.ctx.renderer, cc = r.getClearColor(new THREE.Color()), ca = r.getClearAlpha();
    r.setClearColor(INK, 1);
    st.render(out, { dof: this.focus(t, sew) });
    r.setClearColor(cc, ca);

    // the landing breathes the frame a hair and the light lands with a soft punch and a small settle; the glow opens a
    // little with the lines' light
    const dp = t - T.pull;
    const shake = dp >= 0 ? 0.8 * Math.exp(-dp * 16) * Math.cos(dp * 2 * Math.PI * 8) : 0;
    const zoom = 0.003 * pulse(t, T.answer, 0.1) + 0.003 * pulse(t, T.click, 0.08) + 0.002 * pulse(t, T.strike, 0.12) + 0.006 * pulse(t, T.pull, 0.12);
    const strain = 0.5 * pulse(t, T.pull, 0.1);
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
    for (const x of [this.ink, this.bloom, this.flare, this.rangeGlow, this.sign, this.backdrop]) x?.dispose();
    this.thread?.dispose();
    this.stage?.dispose();
  }
}
