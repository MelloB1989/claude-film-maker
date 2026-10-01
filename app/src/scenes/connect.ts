// Scene 13 `connect`: "One command... and I'm in Claude Code." / "Or any agent, in any language." (Plan 2 Task 23; spec
// §4 13, §11.1–11.3.) The call to action for developers: the slickest onboarding ever shot. Setup is one command, and
// then everything else is one line.
//
// One world and one camera, every time from the data (her measured onsets, the score's beats; connect-time.ts):
// 1. The command. A terminal fills the frame in close 3D, its prompt waiting, breathing a little blood light (the call
//    to act). On "One" (its beat) the Claude Code command (§11.1) types in with her, three lines, a breath at each `\`,
//    the focus riding the typing head as the camera eases back and drifts along it; it is typed by the end of
//    "command…".
// 2. Enter, on the downbeat in her pause: a light runs across the command as it goes, the rows open and the camera drops
//    onto the new prompt. `claude mcp list` types in the rest of the pause and its answer prints as she says "I'm".
// 3. I'm in. On "in" (its beat) the ✔ is drawn into the answer as a moss path (connect-light.ts's Tick): a pen sets down,
//    runs the short arm and flicks up the long one, hot at its head, and the mark flares as it lands and settles to a
//    low glow. The camera all but holds while it draws, then leans in on `✔ Connected`.
// 4. Claude Code. On "Claude" the camera pulls back and up and the terminal turns out to be one face of a carousel:
//    seven faces round a ring in the dark, the six others face down, those round the back falling away into the dark.
// 5. L27, any agent, in any language: on each of the six beats from "Code." to the cut the ring whips round a face and
//    decelerates into the beat, and the card coming round flips over as it lands, face up and still on the beat, a
//    strip softbox's reflection running across its glossy face and glinting off its edge: the MCP config, `gitloom
//    install codex --write` with its hosts, then TypeScript, Python, Go and Rust (§11.2–11.3), each language's name
//    standing on its card in 3D, a light sweeping its bevels as it lands. The camera settles in as the first card
//    lands and drifts round the ring to the cut; the faces off to the sides fall out of focus.
import * as THREE from 'three';
import { Scene, type Frame, type PostOverrides } from '../engine/scene';
import { CameraRig, Stage, type CamKey } from '../engine/stage';
import { W, H, makeRT } from '../engine/gl';
import { Panel } from '../engine/panels';
import { Halo } from '../engine/panel-light';
import { Mat, Type3D, DEPTH } from '../engine/type3d';
import { F } from '../engine/type';
import { sweepAt, withSweep, type SweepBand } from '../engine/sweep';
import { LIN } from '../engine/palette';
import { LOOK } from '../engine/look';
import { clamp, ease, keys, lerp, prog, pulse } from '../engine/util';
import { Backdrop, fitKey } from './diff-fx';
import { FACES, STEP, faceAngle, flipAt, flipStep, penAt, penHeat, tickLevel, timesOf, turnAt, type Times } from './connect-time';
import { NAME, ROW, SIZE, cardSpecs, copyOf, faceOf, sdkLayout, terminalSpec, type Copy } from './connect-cards';
import { CHECK_MID, Gloss, Sheen, Tick } from './connect-light';
import S from './connect.strings.json';

// ------------------------------------------------------------------------------------------------ the world (metres)

/** The lens: a short tele (24° vertical, repo's and diff's). */
const FOV = 24;
/** World units per panel px ×1000 (each face's group scale): a face is about 62 cm wide, its code 13.6 mm to the em. */
const FACE_SCALE = 0.4;
const PX = FACE_SCALE / 1000;
/** The gap between neighbouring faces round the ring (panel px, at their near edges). */
const GAP = 240;
/** The 3D names: their family, and how far they stand off the card (px) beyond their own depth. */
const NAME_FAMILY = F.display(100, 600);
const NAME_LIFT = 3;
/**
 * The strip softbox the faces' gloss reflects (world direction toward it): off to the right of the camera and a touch
 * low, so a face square to the camera shows none of it, and a card swinging in from the right runs through it as it
 * comes round into the front.
 */
const SOFTBOX = new THREE.Vector3(Math.sin(THREE.MathUtils.degToRad(34)), -0.05, Math.cos(THREE.MathUtils.degToRad(34))).normalize();

/** How far the faces round the back of the ring fall into the dark (their opacity there). */
const DEPTH_FADE = 0.3;

const INK = new THREE.Color().setRGB(...LIN.ink);

interface Face {
  /** Turns the face round the ring's axis to its place; the face's own group sits out on the ring in it. */
  pivot: THREE.Group;
  g: THREE.Group;
  panel: Panel;
  /** The softbox's reflection in the face as it turns. */
  gloss: Gloss;
  /** A card's back while it lies face down: a plain face, its front never seen. */
  blank: Panel | null;
  /** An SDK card's name in 3D, its material and the band of light that sweeps it. */
  name: { type: Type3D; mat: THREE.MeshPhysicalMaterial; band: SweepBand } | null;
}

export default class Connect extends Scene {
  private T!: Times;
  private copy!: Copy;
  private face!: { w: number; h: number };
  private stage!: Stage;
  private rig!: CameraRig;
  private ring = new THREE.Group();
  /** The ring's radius (world). */
  private R = 0;
  private faces: Face[] = [];
  private tick!: Tick;
  private halo!: Halo;
  /** The light across the command as Enter sends it, and the blood light the waiting prompt breathes. */
  private sheen!: Sheen;
  private prompt!: Halo;
  private promptAt = { x: 0, y: 0 };
  private backdrop!: Backdrop;

  override init() {
    const { renderer, vo, audio, start, end } = this.ctx;
    this.T = timesOf(vo, audio, start, end);
    this.copy = copyOf(S as string[]);
    this.face = faceOf(this.copy);
    this.stage = new Stage(renderer, { fov: FOV, near: 0.01, far: 30, envIntensity: 0.22 });
    this.buildRing();
    this.buildLights();
    this.backdrop = new Backdrop([12, 7]);
    this.backdrop.mesh.position.set(0, 0, -2.4);
    this.stage.scene.add(this.backdrop.mesh);
    this.rig = new CameraRig(this.keys());
    this.warmUp();
  }

  // ---------------------------------------------------------------------------------------------- the carousel

  private buildRing() {
    const { w, h } = this.face;
    this.R = ((w / 2 + GAP / 2) / Math.tan(Math.PI / FACES)) * PX;
    const specs = [terminalSpec(this.copy, this.T), ...cardSpecs(this.copy)];
    const sdk = sdkLayout(h);
    specs.forEach((spec, k) => {
      const pivot = new THREE.Group(), g = new THREE.Group();
      pivot.rotation.y = k * STEP;
      g.position.set(0, 0, this.R);
      g.scale.setScalar(FACE_SCALE);
      const panel = new Panel(spec);
      const gloss = new Gloss(this.face);
      g.add(panel.mesh, gloss.mesh);
      // (painted, once, at a sliver of the resolution: a face is plain; a Panel never painted samples no map and
      // renders NaN, which the depth of field spreads into black holes)
      const blank = k > 0 ? new Panel({ kind: 'card', w, h, lines: [] }, 0.25) : null;
      if (blank) g.add(blank.mesh);
      let name: Face['name'] = null;
      const lang = k >= 3 ? this.copy.sdks[k - 3]!.lang : null;
      if (lang) {
        const mat = Mat.satinBone();
        const band = withSweep(mat);
        const type = new Type3D(lang, { family: NAME_FAMILY, size: NAME.px / 1000 }, mat);
        // standing on the card, its back a hair off the face: the name is raised lettering, proud of the card
        type.group.position.set((sdk.x - w / 2) / 1000, (h / 2 - sdk.base) / 1000, (DEPTH * NAME.px + NAME_LIFT) / 1000);
        g.add(type.group);
        name = { type, mat, band };
      }
      pivot.add(g);
      this.ring.add(pivot);
      this.faces.push({ pivot, g, panel, gloss, blank, name });
    });
    this.stage.scene.add(this.ring);
    // the ✔ and its light, on the terminal's answer; the light across the command; the prompt's blood light
    const term = this.term(), cell = term.cellOrigin(ROW.out, this.copy.tick);
    this.tick = new Tick({ w, h }, SIZE, cell.x, cell.baseline);
    this.halo = new Halo({ w, h }, 'moss', 0.9 * SIZE);
    this.sheen = new Sheen(this.face);
    this.prompt = new Halo({ w, h }, 'blood', 1.1 * SIZE);
    const $ = term.textOrigin(0);
    this.promptAt = { x: $.x - 2 * term.adv + 0.3 * SIZE, y: $.baseline - 0.36 * SIZE };
    this.faces[0]!.g.add(this.tick.mesh, this.halo.mesh, this.sheen.mesh, this.prompt.mesh);
  }

  private term() {
    return this.faces[0]!.panel;
  }

  /** A point on face 0 (px from its top left, y down; z px out of its face) where it stands in front, in the world. */
  private px(x: number, y: number, z = 0) {
    const { w, h } = this.face;
    // in front, unturned: the face's group at (0, 0, R), square to +z
    return new THREE.Vector3((x - w / 2) * PX, (h / 2 - y) * PX, this.R + z * PX);
  }

  /** The frame face 0 stands in at the front (its right, up and front: the world's axes), for fitKey. */
  private frontFrame() {
    return new THREE.Matrix4().makeTranslation(0, 0, this.R);
  }

  private poseRing(t: number) {
    const T = this.T, { w, h } = this.face, sdk = sdkLayout(h), turn = turnAt(t, T.cards);
    // (the gloss is quieter on the terminal while the camera is in close on it)
    const carousel = prog(t, T.reveal.at, T.reveal.end);
    this.ring.rotation.y = -turn;
    this.faces.forEach((f, k) => {
      f.g.rotation.y = flipAt(t, k, T.cards);
      // the faces round the back of the ring fall away into the dark
      const front = (1 + Math.cos(faceAngle(k, turn))) / 2;
      f.panel.opacity = lerp(DEPTH_FADE, 1, front);
      if (f.blank) f.blank.opacity = f.panel.opacity;
      // a card is its blank back until its flip begins (its back to the camera then, so the change is unseen)
      const up = k === 0 || flipStep(t, T.cards[k - 1]!) > 0;
      f.panel.mesh.visible = f.gloss.mesh.visible = up;
      if (f.blank) {
        f.blank.mesh.visible = !up;
        if (!up) f.blank.draw(t);
      }
      if (f.name) f.name.type.group.visible = up;
      if (up) f.panel.draw(t);
      // the gloss: the softbox runs across a face as it turns through its reflection, glinting off its edge
      if (up) f.gloss.set(SOFTBOX, lerp(0.025, 0.09, carousel), lerp(0.25, 0.9, carousel));
      // and a light across the name's bevels as it lands (world x at the front, where it lands)
      if (f.name) {
        const em = NAME.px * PX, left = (sdk.x - w / 2) * PX, right = left + f.name.type.width * FACE_SCALE;
        const at = T.cards[k - 1]!;
        sweepAt(f.name.band, t, [{ t0: at - 0.04, t1: at + 0.5, x0: left - em, x1: right + em, y: (h / 2 - sdk.base) * PX }], { width: 0.42 * em, strength: 2.6 });
      }
    });
    // Enter: a light runs across the command as it goes
    const u = prog(t, T.enter - 0.16, T.enter + 0.3);
    const on = u > 0 && u < 1 ? Math.sin(Math.PI * u) : 0;
    this.sheen.set(lerp(-0.2 * w, 0.9 * w, ease.inOutQuad(u)), 0.14 * w, 0.04 * on, 0.35 * on);
    // the waiting prompt breathes a little blood light, the call to act, and lets it go as the keys start
    const breath = 0.5 - 0.5 * Math.cos(Math.max(0, t - T.start) * 2 * Math.PI / (2 * T.beat));
    this.prompt.set(this.promptAt.x, this.promptAt.y, (0.18 + 0.22 * breath) * (1 - prog(t, T.type.at - 0.05, T.type.at + 0.25)));
    // the ✔: drawn on by the pen, landing on its beat, lit, a little moss light round it as it lands
    const pen = penAt(t, T.tick), lit = tickLevel(t, T);
    this.tick.set(pen, penHeat(t, T.tick), Math.max(LIN.moss[1], lit), pen > 0 ? 0.03 + 0.03 * lit : 0);
    const cell = this.term().cellOrigin(ROW.out, this.copy.tick);
    const flare = t >= T.tick ? Math.exp(-(t - T.tick) / 0.2) : 0;
    this.halo.set(cell.x + CHECK_MID.x * SIZE, cell.baseline - CHECK_MID.y * SIZE, pen >= 1 ? 0.12 * clamp(lit / 1.1) + 0.35 * flare : 0.15 * pen);
  }

  // ---------------------------------------------------------------------------------------------- the camera

  /** World points boxing face-0 px [x0, x1] × [y0, y1] (z px out of its face). */
  private box(x0: number, y0: number, x1: number, y1: number, z = 0) {
    return [this.px(x0, y0, z), this.px(x1, y0, z), this.px(x0, y1, z), this.px(x1, y1, z)];
  }

  private keys(): CamKey[] {
    const T = this.T, term = this.term(), F = this.frontFrame(), { w, h } = this.face;
    const top = (i: number) => term.rowTop(i), lh = term.lineH;
    const cell = (i: number, c: number) => term.cellOrigin(i, c).x;
    const x0 = term.layout.textX;
    const cmd = this.box(x0 - 40, top(0) - 24, cell(0, 39), top(2) + lh + 6);
    const waiting = this.box(x0 - 3 * term.adv, top(0) - 20, cell(0, 22), top(1) + lh);
    return [
      // the prompt waits, its blood light breathing, the camera in close on it from the left, easing back as she starts
      fitKey(T.start, waiting, { az: -19, el: 5, fov: FOV, margin: [0.02, 0.2], bias: [0.1, -0.02], roll: -2 }, F),
      fitKey(T.type.at, waiting, { az: -18, el: 5, fov: FOV, margin: [0.0, 0.17], bias: [0.08, -0.02], roll: -1.9 }, F, ease.inOutQuad),
      fitKey(T.type.at + 0.38, cmd, { az: -14, el: 5, fov: FOV, margin: [0.04, 0.16], bias: [0.04, -0.04], roll: -1.6 }, F, ease.inOutQuad),
      // drifting with the command as it types, the whole of it in frame
      fitKey(T.type.end, cmd, { az: -12, el: 4.5, fov: FOV, margin: [0.05, 0.14], bias: [0, -0.03], roll: -1.4 }, F, ease.inOutQuad),
      // Enter on the downbeat: the camera drops onto the new prompt and the answer's row
      fitKey(T.enter + 0.2, this.box(x0 - 50, top(1), cell(ROW.out, 46), top(ROW.prompt) + lh), { az: -11, el: 4, fov: FOV, margin: [0.05, 0.12], bias: [0, 0.02], roll: -1.1 }, F, ease.outCubic),
      // the answer prints and the ✔ is drawn: the camera all but holds, so the pen reads, and leans in a hair as it lands
      fitKey(T.out, this.box(x0 - 30, top(ROW.list) - 20, cell(ROW.out, 46), top(ROW.prompt) + lh), { az: -10, el: 4, fov: FOV, margin: [0.05, 0.14], bias: [0, 0.02], roll: -1 }, F, ease.inOutQuad),
      fitKey(T.tick + 0.04, this.box(x0 - 10, top(ROW.list) - 10, cell(ROW.out, 46), top(ROW.prompt) + 0.8 * lh), { az: -9.5, el: 4, fov: FOV, margin: [0.05, 0.13], bias: [0, 0.02], roll: -0.9 }, F, ease.inOutQuad),
      fitKey(T.reveal.at, this.box(cell(ROW.out, 3), top(ROW.list), cell(ROW.out, 46), top(ROW.prompt) + 0.6 * lh), { az: -9, el: 3.8, fov: FOV, margin: [0.05, 0.13], bias: [0, 0.02], roll: -0.8 }, F, ease.linear),
      // Claude Code: the pull back and up to the carousel, the terminal one face of a ring of them
      fitKey(T.reveal.end, this.box(-30, -20, w + 30, h + 20), { az: 8, el: 9.5, fov: FOV, margin: [0.22, 0.25], bias: [0, -0.08], roll: 0.5 }, F, ease.inOutCubic),
      // settling in as the first card flips in, to read them
      fitKey(T.cards[0]! + 0.3, this.box(-30, -20, w + 30, h + 20), { az: 4, el: 7, fov: FOV, margin: [0.13, 0.2], bias: [0, -0.05], roll: 0.2 }, F, ease.inOutQuad),
      // and drifting round it as they do
      fitKey(T.end, this.box(-30, -20, w + 30, h + 20), { az: -6, el: 5.5, fov: FOV, margin: [0.1, 0.18], bias: [0, -0.04], roll: -0.3 }, F, ease.inOutQuad),
    ];
  }

  /** Focus (diopters): the prompt, the typing head, the new prompt, the ✔, then the face in front. */
  private focus(t: number) {
    const T = this.T, st = this.stage, term = this.term();
    const inv = (p: THREE.Vector3) => 1 / Math.max(0.03, st.depthOf(p));
    const lh = term.lineH, mid = (i: number) => term.rowTop(i) + lh / 2;
    const lines = term.spec.lines;
    // the typing head, as an even run along each line (not the frame's keys: the ring of focus turns smoothly)
    const head = (i: number) => {
      const l = lines[i]!, n = Array.from(l.text).length;
      const col = clamp((t - l.at!) * l.cps!, 0, n);
      return inv(this.px(term.cellOrigin(i, col).x, mid(i)));
    };
    const cmd = ROW.cmd.findLast((i) => t >= lines[i]!.at!) ?? 0;
    const ks: [number, number, ((x: number) => number)?][] = [
      [T.start, inv(this.px(term.cellOrigin(0, 8).x, mid(0)))],
      [T.type.at, inv(this.px(term.cellOrigin(0, 8).x, mid(0)))],
    ];
    const typing = t >= T.type.at && t < T.type.end + 0.1 ? head(cmd) : inv(this.px(term.cellOrigin(1, 24).x, mid(1)));
    ks.push([T.type.at + 0.2, typing, ease.inOutQuad], [T.type.end + 0.1, typing]);
    ks.push([T.list.at + 0.1, inv(this.px(term.cellOrigin(ROW.list, 10).x, mid(ROW.list))), ease.inOutQuad]);
    const tickP = inv(this.px(term.cellOrigin(ROW.out, this.copy.tick).x, mid(ROW.out)));
    ks.push([T.out, tickP, ease.inOutQuad], [T.reveal.at, tickP]);
    // the face in front (where every card lands)
    const front = inv(new THREE.Vector3(0, 0, this.R));
    ks.push([T.reveal.end, front, ease.inOutCubic], [T.end, front]);
    const fstop = t < T.reveal.at ? 4 : lerp(4, 3.6, prog(t, T.reveal.at, T.reveal.end));
    return { focus: 1 / keys(t, ks), fstop };
  }

  // ---------------------------------------------------------------------------------------------- light

  /** Neutral light for the names in 3D (the panels are unlit): a key from the upper left in front, a hard rim from behind. */
  private buildLights() {
    const s = this.stage.scene, at = new THREE.Vector3(0, 0, this.R);
    const key = new THREE.DirectionalLight(0xffffff, 1.4);
    key.position.copy(at).add(new THREE.Vector3(-1.3, 1.7, 1.9));
    key.target.position.copy(at);
    const fill = new THREE.DirectionalLight(0xffffff, 0.25);
    fill.position.copy(at).add(new THREE.Vector3(1.6, -0.4, 1.4));
    fill.target.position.copy(at);
    const rim = new THREE.DirectionalLight(0xffffff, 3.2);
    rim.position.copy(at).add(new THREE.Vector3(1.4, 1.2, -1.8));
    rim.target.position.copy(at);
    s.add(key, key.target, fill, fill.target, rim, rim.target);
  }

  private poseBackdrop(t: number) {
    const T = this.T;
    // a soft pool of light comes up behind the face in front as the ring is revealed
    const eye = this.stage.camera.position, at = new THREE.Vector3(0, 0, this.R), zb = this.backdrop.mesh.position.z;
    const behind = eye.clone().lerp(at, (zb - eye.z) / (at.z - eye.z));
    const level = 0.1 + 0.35 * prog(t, T.reveal.at, T.reveal.end + 0.4, ease.inOutQuad);
    this.backdrop.set(behind.x - this.backdrop.mesh.position.x, behind.y - this.backdrop.mesh.position.y, 1.5, 0.8, level);
  }

  // ---------------------------------------------------------------------------------------------- render

  /** Draw everything once before the first frame: shaders compile for the stage's target, the panels paint and upload. */
  private warmUp() {
    const st = this.stage, rt = makeRT(W, H), T = this.T;
    const culled: THREE.Object3D[] = [];
    st.scene.traverse((o) => {
      if (o.frustumCulled) (o.frustumCulled = false), culled.push(o);
    });
    this.rig.apply(st.camera, T.cards[2]!);
    this.poseRing(T.tick + 0.05);
    for (const f of this.faces) {
      f.panel.draw(T.end);
      f.blank?.draw(T.start);
      for (const m of [f.panel.mesh, f.gloss.mesh, f.blank?.mesh, f.name?.type.group]) if (m) m.visible = true;
    }
    this.poseBackdrop(T.cards[2]!);
    st.compile();
    st.render(rt, { dof: { focus: 1, fstop: 4 } });
    for (const o of culled) o.frustumCulled = true;
    rt.dispose();
  }

  render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides {
    const t = f.t, T = this.T, st = this.stage;
    this.rig.apply(st.camera, t);
    this.poseRing(t);
    this.poseBackdrop(t);

    const r = this.ctx.renderer, cc = r.getClearColor(new THREE.Color()), ca = r.getClearAlpha();
    r.setClearColor(INK, 1);
    st.render(out, { dof: this.focus(t) });
    r.setClearColor(cc, ca);

    // Enter and the ✔ punch in a hair; each card's landing jolts the frame and punches in (harder on the downbeat)
    let zoom = 0.005 * pulse(t, T.enter, 0.1) + 0.007 * pulse(t, T.tick, 0.12);
    let shake = 0;
    for (const at of T.cards) {
      const k = this.ctx.audio.downbeats.some((d) => Math.abs(d - at) < 1e-6) ? 1.6 : 1;
      zoom += 0.004 * k * pulse(t, at, 0.1);
      if (t >= at) shake += 1.4 * k * Math.exp(-(t - at) * 22) * Math.cos((t - at) * 2 * Math.PI * 9);
    }
    const lit = clamp(tickLevel(t, T) / 2.5);
    return { shake: [0, shake], zoom: 1 + zoom, bloom: LOOK.bloom + 0.1 * lit, vignette: LOOK.vignette + 0.06 * (1 - prog(t, T.reveal.at, T.reveal.end)) };
  }

  override dispose() {
    for (const f of this.faces) {
      f.panel.dispose();
      f.gloss.dispose();
      f.blank?.dispose();
      if (f.name) {
        f.name.type.dispose();
        f.name.mat.dispose();
      }
    }
    this.tick?.dispose();
    this.halo?.dispose();
    this.sheen?.dispose();
    this.prompt?.dispose();
    this.backdrop?.dispose();
    this.stage?.dispose();
  }
}
