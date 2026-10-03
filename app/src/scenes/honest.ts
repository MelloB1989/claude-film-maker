// Scene 11 `honest`: "And when I don't know... ...I say so." (Plan 2 Task 21; spec §4 11.) GitLoom abstains rather
// than guessing: when nothing clears the evidence floor, the engine returns nothing rather than the nearest vector.
//
// The music is out. Restraint is the scene: near-black, one slow fall, quiet type. One world, one camera, every time
// from the data (honest-time.ts), the arms' every pose a pure function of it (honest-fall.ts):
// 1. The question. On the cut `what's my sister's name?` types in at the top: braid's query, centred this time.
// 2. L22. The evidence floor draws across the dark as she says "And", a hairline fading off at both ends, and the three
//    arms reach up out of the dark one after another: thin diff threads, bone at rest, rooted off the frame, each hung
//    nearly taut from its root to a tip under the floor. They search there; on the downbeat where the music drops out
//    they press up to it and quiver against it (the line lifts a little above each) and stop short. Nothing clears it.
//    On "know…" they still.
// 3. The silence. From the beat after, one by one, they go slack and fall, in slow motion: a ripple runs down each from
//    its tip as the tension leaves it, a faint flicker of blood light riding it (filtered out), and the tip drops, the
//    catenary deepening, undulating, its free end trailing, the root letting go after it, until the frame is empty: the
//    dark, the floor, and the question's caret blinking, waiting.
// 4. L23. With her "…I" a small response card comes up under the floor, the real shape of the response:
//    `"memories": []`, `"candidates": 2`, `"filtered_out": 2`. On "say", on its downbeat, I don't know. comes into
//    focus, quiet, centred, flat light bone, the card stepping back; and the footnote types in under the card, verbatim:
//    the engine returns nothing rather than the nearest vector.
import * as THREE from 'three';
import { Scene, disposeLayer, type Frame, type PostOverrides } from '../engine/scene';
import { Stage } from '../engine/stage';
import { H, Layer2D, W, makeRT } from '../engine/gl';
import { Panel, panelLayout, type PanelLine, type PanelSpec } from '../engine/panels';
import { DIFF_THREAD, Thread, envelopeOf } from '../engine/thread3d';
import { LIN } from '../engine/palette';
import { LOOK, glow } from '../engine/look';
import { ease, frameIdx, hash, prog } from '../engine/util';
import { ARMS, timesOf, type Arm, type Times } from './honest-time';
import { FLOOR_Y, FOV, FSTOP, N_PTS, RADIUS, armAt, cameraAt, reachAt, toVectors, type V3 } from './honest-fall';
import { dim, drawEmber, drawFloor, drawKnow, drawNote, drawQuery, nearness } from './honest-type';
import S from './honest.strings.json';

// ------------------------------------------------------------------------------------------------ the copy

const [QUESTION, OPEN, MEMORIES, CANDIDATES, FILTERED, CLOSE, COMMA, NOTE_TEXT, KNOW_TEXT] =
  S as string[] as [string, string, string, string, string, string, string, string, string];

// ------------------------------------------------------------------------------------------------ the card

/** The card's code size (panel px). */
const CARD_SIZE = 22;
/** Where the card stands on screen once it is up (its top's centre, logical px), and the footnote under it. */
const CARD_TOP = 642;
const NOTE_BELOW = 50;

/**
 * The response, real shape (spec §4 11, §11.10): a JSON object of the three fields, `[]` in the brightest tone. It
 * arrives whole (the card fades up with her "…I").
 */
export function cardSpec(): PanelSpec {
  const field = (s: string, last = false) => `  ${s}${last ? '' : COMMA}`;
  const mem = field(MEMORIES);
  const arr = mem.indexOf('[]');
  const lines: PanelLine[] = [
    { text: OPEN },
    { text: mem, spans: [{ from: arr, to: arr + 2, tone: 'kw' }] },
    { text: field(CANDIDATES) },
    { text: field(FILTERED, true) },
    { text: CLOSE },
  ];
  const g = panelLayout({ kind: 'card', size: CARD_SIZE, lines });
  const cols = Math.max(...lines.map((l) => Array.from(l.text).length));
  const w = Math.ceil((g.textX + cols * g.adv + g.padX + 10) / 2) * 2;
  const h = Math.ceil(g.bar + g.padTop + lines.length * g.lineH + g.padBottom);
  return { kind: 'card', lang: 'json', size: CARD_SIZE, w, h, lines };
}

// ------------------------------------------------------------------------------------------------ the arms' light

/**
 * The blood flicker as an arm lets go: it rides the release ripple from the tip toward the root (honest-fall.ts
 * waveAt), lighting the blood strand there (to the diff thread's lit level) and, since a strand a few metres off is
 * under a pixel wide, an ember of blood light along the thread on screen (its look.ts glow level, and its half-width
 * along the thread, arc fraction).
 */
const FLICKER = { lit: DIFF_THREAD.glow, glow: 1.9, width: 0.045 };

/** The flicker's unevenness: a quick flutter on the frame grid (one state per output frame), never quite out. */
const flicker = (t: number, seed: number) => 0.6 + 0.4 * hash(frameIdx(t), seed);

const INK = new THREE.Color().setRGB(...LIN.ink);

/**
 * The hush (0..1): from `QUIET.lead` s before the scene's end the question, the floor, the card and the footnote let go,
 * until only I don't know. is left, `QUIET.after` s past the end (honest runs on into its tail under the dissolve).
 */
export const QUIET = { lead: 0.3, after: 0.12 };
export const quietAt = (t: number, T: Pick<Times, 'end'>) => prog(t, T.end - QUIET.lead, T.end + QUIET.after, ease.inOutCubic);
/**
 * honest → proof dissolves (transitions/honest-proof.ts): honest runs on past its end under proof's drums, I don't
 * know. alone and the caret still blinking, rather than freezing. All engine-built, every pose from t.
 */
export const HANDLES = { head: 0, tail: 0.5 };

export default class Honest extends Scene {
  override handles = HANDLES;
  private T!: Times;
  private stage!: Stage;
  private threads = {} as Record<Arm, Thread>;
  private vecs = {} as Record<Arm, THREE.Vector3[]>;
  private card!: Panel;
  private cardG = new THREE.Group();
  private layer = new Layer2D();
  /** The embers' light, low-res (it is soft), composited as blood glow. */
  private glowLayer = new Layer2D(W, H, 1);
  private v = new THREE.Vector3();
  /** The card's world scale and place (it stands at CARD_TOP on screen when "say" lands). */
  private cardHome = new THREE.Vector3();

  override init() {
    const { renderer, vo, audio, start, end } = this.ctx;
    const T = (this.T = timesOf(vo, audio, start, end));
    this.stage = new Stage(renderer, { fov: FOV, near: 0.05, far: 40, envIntensity: 0.14 });
    const s = this.stage.scene;

    // the arms: thin diff threads, bone at rest (their strands dark), built on the reach they settle into (no fibres off
    // them: at a few px across they would be under a pixel)
    for (const a of ARMS) {
      const pts = reachAt(a, T.rise(a) + 0.6, T).pts;
      const th = new Thread(toVectors(pts, []), { ...DIFF_THREAD, radius: RADIUS, fuzz: 0, radialSegments: 10, tubularSegments: 640, seed: 0x5ee0 + ARMS.indexOf(a) });
      th.setStrandLight({}, FLICKER.lit); // the strip's program, compiled in the warm-up
      this.threads[a] = th;
      this.vecs[a] = [];
      s.add(th.mesh);
    }

    // neutral light only (lit bone stays out of the bloom), all of it close over the tips, so the light pools where the
    // search is: the arms fall away into the dark toward their roots, and as they fall they fall out of the light. Two
    // keys above the floor on either side and a little in front, each laying a highlight along the arms that run square
    // to it, and a rim behind them that draws their edges out of the dark.
    const keyL = new THREE.PointLight(0xffffff, 2.4, 0, 2);
    keyL.position.set(-0.35, 0.95, 0.65);
    const keyR = new THREE.PointLight(0xffffff, 1.9, 0, 2);
    keyR.position.set(0.75, 0.9, 0.55);
    const rim = new THREE.PointLight(0xffffff, 20, 0, 2);
    rim.position.set(0.2, 1.2, -1.6);
    s.add(keyL, keyR, rim);

    // the card: in the plane of the tips (in focus), facing the lens with the slightest turn
    const spec = cardSpec();
    this.card = new Panel(spec);
    this.cardG.add(this.card.mesh);
    this.cardG.rotation.set(-0.025, 0.04, 0);
    s.add(this.cardG);
    this.placeCard();
    this.warmUp();
  }

  /** Where the card lives: its top's centre at CARD_TOP on screen through the camera at "say", in the plane z = 0, at
   * one panel px to the screen px there. */
  private placeCard() {
    const cam = this.stage.camera;
    this.aim(this.T.say);
    const ppu = this.ppuAt(0);
    const k = 1000 / ppu;
    this.cardG.scale.setScalar(k);
    const top = this.unproject(960, CARD_TOP);
    const h = this.card.spec.h / 1000;
    this.cardHome.set(top.x, top.y - (h * k) / 2, 0);
    this.cardG.position.copy(this.cardHome);
    cam.updateMatrixWorld();
  }

  /** Logical px per world unit in the plane z = `z` (the camera looks square at it). */
  private ppuAt(z: number) {
    const cam = this.stage.camera;
    const d = cam.position.z - z;
    return H / 2 / (d * Math.tan((cam.fov * Math.PI) / 360));
  }

  /** The point of the plane z = 0 under logical px (x, y), through the camera as it is. */
  private unproject(x: number, y: number) {
    const cam = this.stage.camera;
    const p = this.v.set((x / W) * 2 - 1, 1 - (y / H) * 2, 0.5).unproject(cam);
    const dir = p.sub(cam.position);
    const s = -cam.position.z / dir.z;
    return cam.position.clone().addScaledVector(dir, s);
  }

  /** A world point on screen (logical px), through the camera as it is. */
  private toScreen(p: V3): { x: number; y: number; z: number } {
    const q = this.v.set(p[0], p[1], p[2]).project(this.stage.camera);
    return { x: ((q.x + 1) / 2) * W, y: ((1 - q.y) / 2) * H, z: q.z };
  }

  /** The camera at t (cameraAt: level, square to the floor's plane). */
  private aim(t: number) {
    const cam = this.stage.camera, c = cameraAt(t, this.T);
    cam.fov = FOV;
    cam.position.set(...c.pos);
    cam.up.set(0, 1, 0);
    cam.lookAt(...c.target);
    cam.updateProjectionMatrix();
    cam.updateMatrixWorld();
  }

  /**
   * Draw everything once before the first frame: the threads' programs (with their strand light), the card's, the
   * stage's passes. Nothing it sets outlives it: render() sets all state from t.
   */
  private warmUp() {
    const st = this.stage, rt = makeRT(W, H), T = this.T, { renderer, comp } = this.ctx;
    this.aim(T.hush);
    for (const a of ARMS) this.poseArm(a, T.hush);
    this.card.opacity = 1;
    this.card.draw(T.end);
    this.cardG.visible = true;
    st.compile();
    st.render(rt, { dof: { focus: 4.5, fstop: FSTOP } });
    // the layers' textures and the composites they go through: the embers' (added as blood light) and the type's (with
    // I don't know. caught mid-focus, under its blur)
    this.glowLayer.clear();
    comp.draw(renderer, this.glowLayer.upload(), rt, { mode: 'add', tint: glow('blood', FLICKER.glow) });
    this.layer.clear();
    drawKnow(this.layer.ctx, T.say + 0.1, KNOW_TEXT, T.say);
    comp.draw(renderer, this.layer.upload(), rt);
    rt.dispose();
  }

  /**
   * Arm `a` at t: its centreline, draw window, and the blood flicker riding its release ripple down the strand. Returns
   * its pose and the flicker's strength there (for the ember on screen).
   */
  private poseArm(a: Arm, t: number) {
    const th = this.threads[a], T = this.T;
    const pose = armAt(a, t, T);
    th.setPoints(toVectors(pose.pts, this.vecs[a]));
    th.setDraw(pose.draw[0], Math.max(pose.draw[1], 1e-4));
    th.mesh.visible = pose.draw[1] > 0.002;
    const flare = pose.wave.k * flicker(t, ARMS.indexOf(a) + 11);
    th.setStrandLight({ blood: flare > 0.002 ? envelopeOf([{ u: pose.wave.u, w: FLICKER.width, k: flare }]) : null }, FLICKER.lit);
    return { ...pose, flare };
  }

  render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides {
    const { renderer, comp } = this.ctx;
    const t = f.t, T = this.T, st = this.stage;
    this.aim(t);

    // ---- the arms; each hidden once every point of it is below the frame
    const tips: { x: number; near: number }[] = [];
    const embers: { pts: { x: number; y: number }[]; u: number; k: number }[] = [];
    const floorY = this.toScreen([st.camera.position.x, FLOOR_Y, 0]).y;
    for (const a of ARMS) {
      const pose = this.poseArm(a, t);
      if (pose.flare > 0.004) embers.push({ pts: pose.pts.map((p) => this.toScreen(p)), u: pose.wave.u, k: pose.flare });
      if (pose.slack > 0 && t > T.slack(a) + 0.3) {
        const gone = pose.pts.every((p) => this.toScreen(p).y > H + 12);
        if (gone) this.threads[a].mesh.visible = false;
      }
      // the head of the drawn thread (the tip once it is up), and how close it is to the floor
      const head = pose.pts[Math.round(pose.draw[1] * (N_PTS - 1))]!;
      const sp = this.toScreen(head);
      tips.push({ x: sp.x, near: nearness(sp.y - floorY) * (1 - pose.slack) * (pose.draw[1] > 0.6 ? 1 : 0) });
    }

    // ---- the hush before the dissolve (honest → proof): everything around I don't know. leaves, so the line is alone
    // when proof's drums come up through it
    const still = 1 - quietAt(t, T);

    // ---- the card: up with her "…I", rising a hair as it fades in
    const up = prog(t, T.respond - 0.06, T.respond + 0.3, ease.outCubic);
    this.cardG.visible = up > 0;
    if (up > 0) {
      const k = this.cardG.scale.x;
      this.cardG.position.copy(this.cardHome).add(this.v.set(0, (-10 * (1 - up) * k) / 1000, 0));
      // it steps back a little as I don't know. lands, so the line leads
      this.card.opacity = up * dim(t, T.say, T.say + 0.5, 1, 0.84) * still;
      this.card.draw(t);
    }

    const r = renderer, cc = r.getClearColor(new THREE.Color()), ca = r.getClearAlpha();
    r.setClearColor(INK, 1);
    st.render(out, { dof: { focus: st.depthOf([st.camera.position.x, FLOOR_Y, 0]), fstop: FSTOP } });
    r.setClearColor(cc, ca);

    // ---- the embers of blood light running down the arms as they let go
    if (embers.length) {
      const G = this.glowLayer;
      G.clear();
      for (const e of embers) drawEmber(G.ctx, e.pts, e.u, FLICKER.width, e.k);
      comp.draw(renderer, G.upload(), out, { mode: 'add', tint: glow('blood', FLICKER.glow) });
    }

    // ---- the flat type and the floor
    const L = this.layer, c = L.ctx;
    L.clear();
    c.textBaseline = 'alphabetic';
    const n = Array.from(QUESTION).length;
    const cps = (n - 1) / (T.asked - T.ask);
    drawQuery(c, t, QUESTION, T.ask, cps, dim(t, T.respond - 0.1, T.say + 0.3, 1, 0.5) * still, T.respond);
    const floorA = dim(t, T.say, T.say + 0.5, 1, 0.55) * still;
    drawFloor(c, floorY, prog(t, T.floor.at, T.floor.end), floorA, tips);
    drawKnow(c, t, KNOW_TEXT, T.say);
    if (up > 0) {
      const bottom = this.cardBottom();
      drawNote(c, t, NOTE_TEXT, T.note, bottom.x, bottom.y + NOTE_BELOW, still);
    }
    comp.draw(renderer, L.upload(), out);

    // the room darkens a little as the music drops out
    return { vignette: LOOK.vignette + 0.08 * prog(t, T.hush - 0.2, T.hush + 0.8, ease.inOutQuad) };
  }

  /** The card's bottom edge's middle on screen (logical px), as it stands now. */
  private cardBottom() {
    const h = this.card.spec.h / 1000;
    const p = this.v.set(0, -h / 2, 0);
    this.card.mesh.localToWorld(p);
    return this.toScreen([p.x, p.y, p.z]);
  }

  override dispose() {
    for (const a of ARMS) this.threads[a]?.dispose();
    this.card?.dispose();
    this.stage?.dispose();
    disposeLayer(this.layer);
    disposeLayer(this.glowLayer);
  }
}

