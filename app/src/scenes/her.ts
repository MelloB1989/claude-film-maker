// Scene 03 `her`: "Not me." / "Every memory… a commit." / "Every fact… a blame." The headline slam: the look test's
// typographic hero (Plan 2 Task 10; spec §4 03).
//
// One world, three shots, every time from the data (the voiceover's measured onsets, the score's beats):
// 1. The thread. Black, then the diff thread whips in from frame left and pulls taut, the camera riding along it in a
//    slow macro push. On "Not" it snaps taut and a specular sweep runs along it; on "me." it hums.
// 2. The bead. On the downbeat after "me." (the score opens) the camera whips along the thread onto the commit bead,
//    a satin-glass sphere engraved 3f9a1c2, sliding onto the thread and settling in the rim light.
// 3. The headline. A hard cut on the next beat to the site's headline hanging in the dark: `− your agent forgets`,
//    small, struck through in blood on the cut; then `+ every memory has a commit` and `+ every fact has a blame` type
//    in with her, the hero words slamming in from depth on their onsets as extruded satin bone ("commit" and "blame"
//    with the moss diff glow), a light glinting across each as it lands, "every" flat and "has a" flat and quiet. The
//    camera tracks the first + line and comes round low onto "commit" (the hero), then pulls out to the whole headline
//    and orbits it; light, focus and a pool on the backdrop follow each hero word as it lands. On "blame" the blame
//    gutter slides in at left. Then the whole headline drifts back out of focus.
import * as THREE from 'three';
import { RectAreaLightUniformsLib } from 'three/examples/jsm/lights/RectAreaLightUniformsLib.js';
import { Scene, type Frame, type PostOverrides } from '../engine/scene';
import { CameraRig, Stage, type CamKey, type V3 } from '../engine/stage';
import { H, W, makeRT } from '../engine/gl';
import { Thread } from '../engine/thread3d';
import { Mat, Type3D } from '../engine/type3d';
import { F } from '../engine/type';
import { LIN } from '../engine/palette';
import { GLOW_LEVEL, glow } from '../engine/look';
import { onBeat, slam, whip, wordTimes } from '../engine/motion';
import { norm, type VO } from '../engine/vo';
import type { AudioData } from '../engine/audio';
import { clamp, ease, keys, lerp, prog, pulse } from '../engine/util';
import { Bead } from './her-bead';
import { Backdrop, DiffLine, FLAT, unlit, withSweep } from './her-type';
import { fitKey } from './her-camera';
import S from './her.strings.json';

// ------------------------------------------------------------------------------------------------ the copy

const [HASH, MINUS_LINE, PLUS_MEMORY, PLUS_FACT, BLAME] = S as [string, string, string, string, string];
/** A diff line's gutter mark and its text: the mark, a space, the text. */
const split = (s: string): [string, string] => [s.slice(0, s.indexOf(' ')), s.slice(s.indexOf(' ') + 1)];

// ------------------------------------------------------------------------------------------------ the world (metres)

/** The headline: world units per em of the + lines; the − line's size (em), as on the site; the + lines' spacing. */
const EM = 0.1;
const SMALL = 0.52;
const LEAD = 1.14;
/** The − line's baseline above the first + line's (em). */
const MINUS_RISE = 1.0;
/** The gutter column: the marks' left edge (em from the text's origin) and size (em). */
const MARK_X = -0.78;
const MARK_SIZE = 0.55;
const TRACK = -0.022;
/** The blame gutter: its mono size (em) and the gap between it and the gutter column (em). */
const BLAME_SIZE = 0.22;
const BLAME_GAP = 0.3;

/** The thread: a long diagonal in the dark, from front left to back right (shots 1 and 2; the headline is shot 3). */
const THREAD_A: V3 = [-1.9, -0.72, 0.62];
const THREAD_B: V3 = [2.8, -0.56, -1.62];
const THREAD_R = 0.0042;
/** A long lay (14° against the default 32°): fewer, longer stripes, a luxury cable rather than a candy cane. */
const LAY_DEG = 14;
const TWIST = Math.tan((LAY_DEG * Math.PI) / 180) / (2 * Math.PI * 0.5 * THREAD_R);
/**
 * The blood and moss strands: colour as light, not paint. Their fibre is dyed near ink (strandDye) and slimmed a little
 * (strandScale), so the colour is carried by the glowing core alone, a thin line of light in the grooves, fibre optic
 * rather than paint. The glow flares on the hits.
 */
const STRAND = { dye: 0.03, scale: 0.62, glow: 3.6 };
const THREAD_GLOW = STRAND.glow;
/** The thread's sag before the snap (world units at its middle), and the whip's wave (world units at the tip). */
const SAG = 0.02;
const WAVE = 0.012;
/** Macro f-numbers: at 10–15 cm the depth of field is millimetres, so the thread and the bead stop down. */
const F_THREAD = 8;
const F_BEAD = 8;
const F_TYPE = 2.8;
/** Where along the thread (arc fraction) shot 1 looks, and where the bead comes to rest. */
const SHOT1_U = 0.26;
const BEAD_U = 0.56;
const BEAD_R = 0.024;
/** Shot 2's camera at the end of the shot, from the bead: out to the viewer's side, up, and back along the thread. At
 * 25 cm on the 24° lens the bead fills about 45% of the frame's height: a product macro, with room round it. */
const BEAD_CAM = { off: 0.216, up: 0.02, along: -0.118 };
/** How far the etched band rises above the bore's equator (radians). */
const ETCH_RISE = 0.4;

type Pose = { pos: THREE.Vector3; quat: THREE.Quaternion; fov: number };
const Y = new THREE.Vector3(0, 1, 0);
const INK = new THREE.Color().setRGB(...LIN.ink);

export default class Her extends Scene {
  private stage!: Stage;
  private thread!: Thread;
  private bead!: Bead;
  private head = new THREE.Group();
  private minus!: DiffLine;
  private plus1!: DiffLine;
  private plus2!: DiffLine;
  private strike!: THREE.Mesh;
  private blame!: Type3D;
  private blameRule!: THREE.Mesh;
  private blameMats: THREE.MeshBasicMaterial[] = [];
  private mats: THREE.Material[] = [];
  private accent: THREE.MeshPhysicalMaterial[] = [];
  /** Each + line's specular sweep (its hero materials share one band). */
  private sweeps: THREE.IUniform<THREE.Vector4>[] = [];
  private backdrop!: Backdrop;
  /** The kicker behind the bead: a softbox whose reflection rings its silhouette out of the ink. */
  private kicker!: THREE.RectAreaLight;
  /** A small softbox whose reflection travels across the bead as it lands (the specular kick). */
  private kick!: THREE.RectAreaLight;
  private sweep!: THREE.PointLight;
  private pool!: THREE.SpotLight;
  private fill!: THREE.PointLight;
  /** Shots 1 and 2 are lit by `thread`, shot 3 by `type`: each light's intensity per set (lights stay in the scene,
   * so the shaders never recompile at the cut). */
  private lights: { light: THREE.Light; thread: number; type: number }[] = [];
  /** Where the bead's face points: square to the bore on the viewer's side (the engraving is centred on the camera). */
  private beadFace = new THREE.Vector3();
  /** Shot 1's push along the thread (world units) over its length, and how far ahead of its point the camera looks. */
  private shot1 = { push: 0.06, ahead: 0.045 };
  private rig1!: CameraRig;
  private rig2!: CameraRig;
  private rig3!: CameraRig;
  private scratch = new THREE.PerspectiveCamera();
  /** Times from the data (song seconds). */
  private T!: ReturnType<typeof timesOf>;
  /** The thread's direction, and the horizontal square to it on the viewer's side. */
  private dir = new THREE.Vector3();
  private side = new THREE.Vector3();

  override init() {
    const { renderer, vo, audio } = this.ctx;
    this.T = timesOf(vo, audio, this.ctx.start, this.ctx.end);
    this.stage = new Stage(renderer, { fov: 24 });
    const s = this.stage.scene;

    // the thread, built at its full length and drawn on (its twist is in material coordinates)
    const A = new THREE.Vector3(...THREAD_A), B = new THREE.Vector3(...THREAD_B);
    this.dir.subVectors(B, A).normalize();
    this.side.set(-this.dir.z, 0, this.dir.x).normalize();
    this.thread = new Thread(this.threadPoints(Infinity), {
      radius: THREAD_R, twist: TWIST, glow: THREAD_GLOW, fuzz: 0.6, strandDye: STRAND.dye, strandScale: STRAND.scale,
    });
    s.add(this.thread.mesh);

    // the engraving faces square to the bore; the camera sees the bead from back along the thread, so the band is
    // centred where it looks, raised above the bore's equator so the frosted letters sit over dark glass, not over the
    // bright thread refracted through the middle of the bead
    const look: [number, number] = [Math.atan2(BEAD_CAM.along, BEAD_CAM.off), Math.atan2(BEAD_CAM.up, Math.hypot(BEAD_CAM.off, BEAD_CAM.along)) + ETCH_RISE];
    this.bead = new Bead({ radius: BEAD_R, bore: THREAD_R * 1.3, chamfer: THREAD_R * 0.7, text: HASH, centre: look });
    s.add(this.bead.mesh);

    this.buildHeadline();
    s.add(this.head);
    // the studio behind the headline: ink that lifts toward panel behind the hero word
    this.backdrop = new Backdrop(LIN.ink, LIN.panel, [14, 7]);
    this.backdrop.mesh.position.set(0.5, 0, -2.4);
    s.add(this.backdrop.mesh);
    this.buildLights();
    this.buildRigs();
    this.warmUp();
  }

  /**
   * Draw every object once at full size before the first frame: shaders compile, geometry and textures upload, and
   * three allocates the bead's transmission target. Otherwise a first-use stall of 100+ ms lands on the frame where the
   * bead or the headline first appears. Nothing it sets outlives it: render() sets all state from t on every frame.
   */
  private warmUp() {
    const st = this.stage, rt = makeRT(W, H);
    const culled: THREE.Object3D[] = [];
    st.scene.traverse((o) => {
      if (o.frustumCulled) (o.frustumCulled = false), culled.push(o);
    });
    this.head.visible = this.thread.mesh.visible = this.bead.mesh.visible = true;
    st.camera.position.set(0.5, 0, 3);
    st.camera.lookAt(0.5, 0, 0);
    st.camera.updateMatrixWorld();
    st.render(rt, { dof: { focus: 3, fstop: 4 } });
    for (const o of culled) o.frustumCulled = true;
    rt.dispose();
  }

  // ---------------------------------------------------------------------------------------------- build

  private buildHeadline() {
    const fam = F.display(100, 600), mono = F.mono(500);
    const m = <M extends THREE.Material>(x: M) => (this.mats.push(x), x);
    const satin = [m(Mat.satinBone()), m(Mat.satinBone())];
    const moss = [m(Mat.accent('moss', 0)), m(Mat.accent('moss', 0))];
    this.accent = moss;
    // one sweep band per + line, over both its hero words
    for (let i = 0; i < 2; i++) {
      const u = withSweep(satin[i]!);
      const v = withSweep(moss[i]!);
      v.value = u.value; // the same Vector4: one band per line
      this.sweeps.push(u);
    }
    const every = m(unlit(scaled(LIN.bone, 0.74)));
    const quiet = m(unlit(LIN.boneDim));
    const faint = m(unlit(LIN.boneFaint));
    const plusMat = m(unlit(LIN.moss));
    const minusMat = m(unlit(LIN.blood));

    const [mm, mt] = split(MINUS_LINE), [p1m, p1t] = split(PLUS_MEMORY), [p2m, p2t] = split(PLUS_FACT);
    this.minus = new DiffLine({
      mark: mm, text: mt, family: F.display(100, 500), markFamily: mono, size: EM * SMALL, tracking: TRACK,
      markSize: 1, markX: MARK_X / SMALL, heroes: [], hero: () => faint, flat: () => faint, markMat: minusMat,
    });
    this.minus.group.position.y = MINUS_RISE * EM;
    const line = (mk: string, text: string, i: number) => new DiffLine({
      mark: mk, text, family: fam, markFamily: mono, size: EM, tracking: TRACK, markSize: MARK_SIZE, markX: MARK_X,
      heroes: [1, 4], hero: (w) => (w === 4 ? moss[i]! : satin[i]!), flat: (w) => (w === 0 ? every : quiet), markMat: plusMat,
    });
    this.plus1 = line(p1m, p1t, 0);
    this.plus2 = line(p2m, p2t, 1);
    this.plus2.group.position.y = -LEAD * EM;
    this.head.add(this.minus.group, this.plus1.group, this.plus2.group);

    // the strike: a hairline of blood through the − line's x-height, drawn on left to right
    const sg = new THREE.PlaneGeometry(1, 1);
    sg.translate(0.5, 0, 0);
    this.strike = new THREE.Mesh(sg, m(unlit(glow('blood', 1.25))));
    this.strike.scale.set(1, 0.07 * EM * SMALL, 1);
    this.strike.position.set(this.minus.wordSpan(0)[0] - 0.04 * EM, 0.29 * EM * SMALL, 0.0015);
    this.minus.group.add(this.strike);

    // the blame gutter: mono, left of the second + line's mark, its hash brightest; a hairline column rule beside it
    const bone = m(unlit(LIN.bone, { transparent: true })), dim = m(unlit(LIN.boneDim, { transparent: true }));
    this.blameMats = [bone, dim];
    const hashEnd = Array.from(HASH).length;
    this.blame = new Type3D(BLAME, { family: F.mono(400), size: EM * BLAME_SIZE, ...FLAT }, (g) => (g.i < hashEnd ? bone : dim));
    this.plus2.group.add(this.blame.group);
    this.blameRule = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), m(unlit(LIN.ruleStrong, { transparent: true })));
    this.blameRule.scale.set(0.012 * EM, 1.0 * EM, 1);
    this.blameRule.position.set((MARK_X - BLAME_GAP / 2) * EM, 0.3 * EM, 0);
    this.plus2.group.add(this.blameRule);
  }

  private buildLights() {
    const s = this.stage.scene;
    // neutral light only (lit bone stays out of the bloom's chroma gate). Shots 1 and 2: a key from the upper left, a
    // softbox in front of it, a hard rim from behind on the right that sculpts the plies, a small fill on the bead's
    // face and a kicker behind it that rings its edge; a point light runs the specular sweep along the thread on
    // "Not". Shot 3, the type: a long softbox overhead whose reflection runs along the top bevels, a raking spot that
    // follows the hero word as it lands (light, focus and type agree on what matters), a low fill, and the rim. (The
    // type's sweeps are in its materials: withSweep.)
    RectAreaLightUniformsLib.init();
    const box = new THREE.RectAreaLight(0xffffff, 1, 1.8, 0.6);
    box.position.set(-0.5, 1.3, 1.5);
    box.lookAt(0.5, 0, 0);
    const top = new THREE.RectAreaLight(0xffffff, 1, 2.4, 0.42);
    top.position.set(0.55, 0.8, 0.42);
    top.lookAt(0.55, 0, -0.05);
    const key = new THREE.DirectionalLight(0xffffff, 1);
    key.position.set(-1.4, 2.2, 1.8);
    key.target.position.set(0.4, -0.3, -0.3);
    const rim = new THREE.DirectionalLight(0xffffff, 1);
    rim.position.set(1.6, 1.6, -3);
    rim.target.position.set(0.4, -0.3, -0.3);
    this.pool = new THREE.SpotLight(0xffffff, 0, 0, THREE.MathUtils.degToRad(24), 0.95, 2);
    this.sweep = new THREE.PointLight(0xffffff, 0, 0, 2);
    this.fill = new THREE.PointLight(0xffffff, 0, 0, 2);
    this.kicker = new THREE.RectAreaLight(0xffffff, 0, 0.34, 0.34);
    this.kick = new THREE.RectAreaLight(0xffffff, 0, 0.02, 0.1);
    s.add(box, top, key, key.target, rim, rim.target, this.pool, this.pool.target, this.sweep, this.fill, this.kicker, this.kick);
    this.lights = [
      { light: box, thread: 0.35, type: 0 },
      { light: top, thread: 0, type: 7 },
      { light: key, thread: 0.3, type: 0.45 },
      { light: rim, thread: 6, type: 2.5 },
    ];
  }

  /** Four world points boxing words w0..w1 of a line (descender to cap height), for framing. */
  private box(l: DiffLine, w0: number, w1: number, withMark = false): THREE.Vector3[] {
    const s = l.solid.size, x0 = withMark ? l.mark.group.position.x : l.wordSpan(w0)[0], x1 = l.wordSpan(w1)[1];
    this.head.updateMatrixWorld(true);
    return [[x0, -0.22 * s], [x1, -0.22 * s], [x0, 0.74 * s], [x1, 0.74 * s]].map(([x, y]) => l.group.localToWorld(new THREE.Vector3(x, y, 0)));
  }

  private buildRigs() {
    const T = this.T, th = this.thread, d = this.dir, n = this.side;
    // shot 1: a macro beside the thread and a little below it, looking along it as it recedes up to the right (the
    // camera rolled so it crosses the frame on a diagonal); a slow push along it. It frames the thread half way
    // between its slack and taut lines, so the snap on "Not" lifts it through the frame.
    const f1 = th.pointAt(SHOT1_U).addScaledVector(Y, -0.5 * SAG * Math.sin(Math.PI * SHOT1_U));
    const at1 = (push: number): [V3, V3] => [
      f1.clone().addScaledVector(n, 0.1).addScaledVector(d, -0.07 + push).addScaledVector(Y, -0.012).toArray() as V3,
      f1.clone().addScaledVector(d, this.shot1.ahead + push).addScaledVector(Y, 0.002).toArray() as V3,
    ];
    const [p0, t0] = at1(0), [p1, t1] = at1(this.shot1.push);
    this.rig1 = new CameraRig([
      { t: T.start, pos: p0, target: t0, fov: 22, roll: -17 },
      { t: T.down, pos: p1, target: t1, roll: -14, ease: ease.linear },
    ]);
    // shot 2: the bead from its near side, a little behind it along the thread so the thread runs away up to the
    // right through it; landing from the whip and pushing in slowly
    const b = th.pointAt(BEAD_U);
    const bp = (off: number, up: number, along: number): V3 => b.clone().addScaledVector(n, off).addScaledVector(d, along).addScaledVector(Y, up).toArray() as V3;
    const bt = (along: number, up = 0): V3 => b.clone().addScaledVector(d, along).addScaledVector(Y, up).toArray() as V3;
    const late = bp(BEAD_CAM.off, BEAD_CAM.up, BEAD_CAM.along), land = bp(1.08 * BEAD_CAM.off, 1.08 * BEAD_CAM.up, 1.08 * BEAD_CAM.along);
    this.beadFace.copy(n);
    this.rig2 = new CameraRig([
      { t: T.down - 0.2, pos: bp(0.28, 0.03, -0.24), target: bt(0.0), fov: 24, roll: -6 },
      { t: T.down + 0.12, pos: land, target: bt(0.012, 0.004), roll: -8, ease: ease.outCubic },
      { t: T.beatAfterDown, pos: late, target: bt(0.012, 0.004), roll: -8.5, ease: ease.linear },
    ]);
    // shot 3: the headline, framed by what shows; every fit keeps its type title-safe (margins of at least 0.1 of the
    // half-width and 0.18 of the half-height: 96 px), except the push through "has a commit", a camera move that crops
    // the line running away from it
    const minus = this.box(this.minus, 0, 2, true);
    const first = this.box(this.plus1, 0, 1, true);
    const line1 = this.box(this.plus1, 0, 4, true);
    // the hero: "memory has a commit", with the struck line whole above it (a crop would change its words)
    const hero = [...this.box(this.plus1, 1, 4), ...this.box(this.minus, 0, 2)];
    const hasCommit = this.box(this.plus1, 2, 4);
    const line2 = this.box(this.plus2, 0, 4, true);
    const blame = this.blameBox();
    const all = [...minus, ...line1, ...line2, ...blame];
    this.rig3 = new CameraRig([
      // the cut: the struck line, close, room below it for what replaces it
      fitKey(T.beatAfterDown, minus, { az: -15, el: 5, fov: 22, margin: [0.2, 0.3], bias: [-0.04, 0.34] }),
      // "Every memory": push in and round as the + line types in beneath
      fitKey(T.every1 + 0.3, [...minus, ...first], { az: -6, el: 3, fov: 22, margin: [0.12, 0.28], bias: [-0.06, 0.06] }, ease.inOutQuad),
      fitKey(T.memory + 0.4, [...minus, ...this.box(this.plus1, 0, 3, true)], { az: 5, el: 1.5, fov: 22, margin: [0.1, 0.28], bias: [-0.04, 0] }, ease.inOutQuad),
      // "commit": the hero, low and from the right, the line running away into the dark
      fitKey(T.commit - 0.08, hero, { az: 35, el: -10, fov: 22, margin: [0.1, 0.28], bias: [0.12, 0.02] }, ease.inOutCubic),
      fitKey(T.commit + 0.45, hero, { az: 37, el: -10, fov: 22, margin: [0.1, 0.28], bias: [0.12, 0.02] }, ease.linear),
      fitKey(T.every2 - 0.12, hasCommit, { az: 39, el: -10.5, fov: 22, margin: [0.1, 0.34], bias: [0.12, 0.04] }, ease.inOutQuad),
      // the carriage return: out to the whole headline (with room at left for the blame gutter to come), then the
      // slow orbit, 30° round to 14°, through "Every fact… a blame."
      fitKey(T.every2 + 0.24, all, { az: 32, el: -4, fov: 24, margin: [0.12, 0.2], bias: [0, 0] }, ease.inOutCubic),
      fitKey(lerp(T.every2 + 0.24, T.end, 0.5), all, { az: 22, el: -2.5, fov: 24, margin: [0.12, 0.2], bias: [0, 0] }, ease.inOutQuad),
      fitKey(T.end, all, { az: 12, el: -1, fov: 24, margin: [0.12, 0.2], bias: [0, 0] }, ease.inOutQuad),
    ]);
  }

  /** The blame gutter's box at rest. */
  private blameBox(): THREE.Vector3[] {
    this.placeBlame(1);
    const s = this.blame.size, x0 = this.blame.group.position.x, x1 = x0 + this.blame.width;
    this.head.updateMatrixWorld(true);
    return [[x0, -0.2 * s], [x1, -0.2 * s], [x0, 0.75 * s], [x1, 0.75 * s]].map(([x, y]) => this.plus2.group.localToWorld(new THREE.Vector3(x, y + this.blame.group.position.y, 0)));
  }

  /** The blame gutter `k` of the way in (0: out to the left, 1: at rest). */
  private placeBlame(k: number) {
    const s = this.blame.size;
    this.blame.group.position.set((MARK_X - BLAME_GAP) * EM - this.blame.width - (1 - k) * 0.1, 0.35 * EM - 0.36 * s, 0);
  }

  // ---------------------------------------------------------------------------------------------- the thread

  /**
   * The thread's centreline at time t: a straight run from A to B that sags a little until the snap on "Not", with a
   * decaying travelling wave while it whips in, and the hum of a plucked string after the snap. (Infinity: at rest.)
   */
  private threadPoints(t: number): THREE.Vector3[] {
    const A = new THREE.Vector3(...THREAD_A), B = new THREE.Vector3(...THREAD_B);
    const T = this.T, side = this.side;
    const N = 48, L = A.distanceTo(B);
    const pts: THREE.Vector3[] = [];
    const rest = !Number.isFinite(t);
    // slack before the snap, taut after it (the spring overshoots a hair: the snap)
    const slack = rest ? 0 : 1 - slam(t, T.not, { freq: 6, damping: 0.55 });
    // the whip: a wave running out along the thread behind the drawn tip, dying as it goes
    const age = rest ? 99 : t - (T.start + 0.04);
    const tip = rest ? 1 : this.tipU(t);
    // the hum after the snap, and again on "me.": a plucked string, a few cycles, decaying
    const pluck = (t0: number, a: number) => (t >= t0 ? a * Math.exp(-(t - t0) * 5.5) * Math.sin((t - t0) * 2 * Math.PI * 7.5) : 0);
    const hum = rest ? 0 : pluck(T.not, 1) + pluck(T.me, 0.45);
    for (let i = 0; i <= N; i++) {
      const u = i / N, p = A.clone().lerp(B, u);
      const bell = Math.sin(Math.PI * u);
      p.addScaledVector(Y, -SAG * slack * bell);
      if (age > -0.1 && age < 1.5) {
        const behind = Math.max(0, tip - u);
        const amp = u < tip ? WAVE * Math.exp(-age * 3.2) * Math.exp(-behind * 2.4) : 0;
        p.addScaledVector(side, amp * Math.sin(behind * L * 7.5));
        p.addScaledVector(Y, 0.5 * amp * Math.cos(behind * L * 6.1));
      }
      p.addScaledVector(Y, 0.0025 * hum * bell);
      pts.push(p);
    }
    return pts;
  }

  /**
   * The drawn tip of the thread (arc fraction): it enters at frame left, crosses the near part of the frame in a fifth
   * of a second, easing as the wave catches up, then races away up the thread into the distance.
   */
  private tipU(t: number) {
    const t0 = this.T.start + 0.05;
    return keys(t, [[t0, 0.236], [t0 + 0.21, 0.302, ease.outCubic], [t0 + 0.42, 1.02, ease.inQuad]]);
  }

  // ---------------------------------------------------------------------------------------------- render

  render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides {
    const t = f.t, T = this.T, st = this.stage, th = this.thread;
    const headline = t >= T.beatAfterDown; // shot 3, after the cut on the beat
    for (const l of this.lights) l.light.intensity = headline ? l.type : l.thread;
    st.scene.environmentIntensity = headline ? 0.28 : 0.2;

    // the thread: whips in (drawn on from the left), pulls taut, snaps on "Not", hums
    th.mesh.visible = !headline;
    if (!headline) {
      th.setPoints(this.threadPoints(t));
      th.setDraw(0, this.tipU(t));
      // the flares stay under the level where a core whitens (about 4 on its brightest channel, look.ts)
      th.setGlow(THREAD_GLOW * (1 + 0.25 * pulse(t, T.not, 0.2) + 0.12 * pulse(t, T.down, 0.28)));
    }

    // the specular sweep on "Not": a light racing along the thread just off its near side
    const sw = prog(t, T.not - 0.02, T.not + 0.36);
    if (sw > 0 && sw < 1) {
      this.sweep.position.copy(th.pointAt(lerp(0.24, 0.32, ease.inOutQuad(sw)))).addScaledVector(this.side, 0.016).addScaledVector(Y, 0.012);
      this.sweep.intensity = 0.03 * Math.sin(Math.PI * sw) ** 1.5;
    } else this.sweep.intensity = 0;

    // the bead threads on from further along the thread, landing on the downbeat as the camera lands on it and turning
    // its face to us; a stiff spring, so it has all but settled a few frames later and its engraving reads
    const bs = slam(t, T.down, { freq: 4.6, damping: 0.72 });
    const fr = th.frameAt(lerp(BEAD_U + 0.035, BEAD_U, bs));
    this.bead.place(fr.pos, fr.tangent, this.beadFace, (1 - bs) * 1.1);
    this.bead.mesh.visible = !headline && t > T.down - 0.15;
    const onBead = this.bead.mesh.visible;
    this.fill.intensity = onBead ? 0.12 : 0;
    this.fill.position.copy(fr.pos).addScaledVector(this.side, 0.2).addScaledVector(Y, 0.12).addScaledVector(this.dir, -0.16);
    // the kicker: a softbox behind the bead and to the right, whose reflection rings its silhouette out of the ink
    this.kicker.intensity = onBead ? 30 : 0;
    this.kicker.position.copy(fr.pos).addScaledVector(this.dir, 0.2).addScaledVector(this.side, -0.26).addScaledVector(Y, 0.14);
    this.kicker.lookAt(fr.pos);
    // the kick: a small softbox swinging round above the camera as the bead lands, so its reflection slides across
    // the glass and the etch catches it
    const kk = prog(t, T.down - 0.04, T.down + 0.5, ease.inOutQuad);
    this.kick.intensity = onBead ? 160 * Math.sin(Math.PI * kk) : 0;
    const toCam = new THREE.Vector3(BEAD_CAM.off, 0, BEAD_CAM.along).normalize(); // in (side, dir) coordinates
    const swing = lerp(-0.95, 0.95, kk), ks = Math.cos(swing) * toCam.x - Math.sin(swing) * toCam.z, kd = Math.sin(swing) * toCam.x + Math.cos(swing) * toCam.z;
    this.kick.position.copy(fr.pos).addScaledVector(this.side, 0.26 * ks).addScaledVector(this.dir, 0.26 * kd).addScaledVector(Y, 0.16);
    this.kick.lookAt(fr.pos);

    // the camera: shot 1 until the whip on the downbeat, the bead until the cut on the next beat, then the headline
    const cam = st.camera;
    let k = 1;
    if (headline) this.rig3.apply(cam, t);
    else {
      const w = whip(t, T.down, 0.11);
      const a = this.pose(this.rig1, t), b = this.pose(this.rig2, t);
      cam.position.lerpVectors(a.pos, b.pos, w.k);
      cam.quaternion.slerpQuaternions(a.quat, b.quat, w.k);
      cam.fov = lerp(a.fov, b.fov, w.k);
      cam.updateProjectionMatrix();
      cam.updateMatrixWorld();
      k = w.k;
    }

    this.head.visible = headline;
    if (headline) this.animateHeadline(t, f);
    else {
      // shots 1 and 2 are the thread in the plain dark: no pool, no backdrop lift (set every frame, as all state is)
      this.pool.intensity = 0;
      this.backdrop.set(0, 0, 1, 1, 0);
    }

    // focus: the thread near shot 1's centre, the bead, then each hero word as it lands (in diopters, as a focus ring)
    let D: number, fstop: number;
    const inv = (p: THREE.Vector3) => 1 / Math.max(0.03, st.depthOf(p));
    if (!headline) {
      // the thread where the camera looks: the push moves the look-at point along it
      const look = SHOT1_U + (this.shot1.ahead + this.shot1.push * prog(t, T.start, T.down)) / this.thread.length();
      const d1 = inv(this.thread.pointAt(look).addScaledVector(this.side, THREAD_R));
      const dBead = inv(this.bead.mesh.position.clone().addScaledVector(this.side, BEAD_R * 0.85));
      D = lerp(d1, dBead, k);
      fstop = lerp(F_THREAD, F_BEAD, k);
    } else {
      D = this.focusDiopters(t);
      fstop = F_TYPE;
    }
    // three clears the bead's transmission pass with the renderer's clear colour: make it ink, what the glass sees
    const r = this.ctx.renderer, cc = r.getClearColor(new THREE.Color()), ca = r.getClearAlpha();
    r.setClearColor(INK, 1);
    st.render(out, { dof: { focus: 1 / D, fstop } });
    r.setClearColor(cc, ca);

    const hit = Math.max(pulse(t, T.memory, 0.08), pulse(t, T.commit, 0.08), pulse(t, T.fact, 0.08), pulse(t, T.blame, 0.08));
    // the snap on "Not" jolts the frame a few px, up then settling (the thread pulls the camera's eye with it)
    const jolt = t >= T.not ? 3.5 * Math.exp(-(t - T.not) * 14) * Math.cos((t - T.not) * 2 * Math.PI * 9) : 0;
    return { zoom: 1 + 0.006 * hit, shake: [0, jolt] };
  }

  private pose(rig: CameraRig, t: number): Pose {
    rig.apply(this.scratch, t);
    return { pos: this.scratch.position.clone(), quat: this.scratch.quaternion.clone(), fov: this.scratch.fov };
  }

  /**
   * Focus in diopters: each hero word as it lands, racked over 0.23 s (as a focus ring turns). Measured where the words
   * rest, so when the headline drifts back on the way out the focus stays where it was and the type goes soft.
   */
  private focusDiopters(t: number) {
    const st = this.stage, T = this.T, drift = this.head.position.z;
    const inv = (p: THREE.Vector3) => 1 / Math.max(0.03, st.depthOf(p));
    this.head.updateMatrixWorld(true);
    const at = (l: DiffLine, w: number) => inv(l.group.localToWorld(l.wordCentre(w)).add(new THREE.Vector3(0, 0, -drift)));
    return keys(t, [
      [T.every1 - 0.08, at(this.minus, 1)],
      [T.memory + 0.05, at(this.plus1, 1), ease.inOutCubic],
      [T.commit - 0.05, at(this.plus1, 1)],
      [T.commit + 0.18, at(this.plus1, 4), ease.inOutCubic],
      [T.fact - 0.05, at(this.plus1, 4)],
      [T.fact + 0.18, at(this.plus2, 1), ease.inOutCubic],
      [T.blame - 0.05, at(this.plus2, 1)],
      [T.blame + 0.18, at(this.plus2, 4), ease.inOutCubic],
      [T.end - 0.42, at(this.plus2, 4)],
      [T.end, at(this.plus2, 4) * 1.18, ease.inQuad],
    ]);
  }

  /** The pool of light on the hero word, and a specular sweep across each hero word as it lands. */
  private lightHeadline(t: number) {
    const T = this.T;
    this.head.updateMatrixWorld(true);
    // the pool eases from word to word with the focus (the point light's sweep is the thread's; off here)
    this.sweep.intensity = 0;
    const spots: [number, THREE.Vector3][] = [
      [T.beatAfterDown, this.minus.group.localToWorld(this.minus.wordCentre(1))],
      [T.memory, this.plus1.group.localToWorld(this.plus1.wordCentre(1))],
      [T.commit, this.plus1.group.localToWorld(this.plus1.wordCentre(4))],
      [T.fact, this.plus2.group.localToWorld(this.plus2.wordCentre(1))],
      [T.blame, this.plus2.group.localToWorld(this.plus2.wordCentre(4))],
    ];
    let aim = spots[0]![1].clone();
    for (let i = 1; i < spots.length; i++) aim.lerp(spots[i]![1], prog(t, spots[i]![0] - 0.06, spots[i]![0] + 0.3, ease.inOutCubic));
    // a raking key close to the hero word from the upper left: the faces fall off across the word, the walls model
    this.pool.position.copy(aim).add(new THREE.Vector3(-0.52, 0.38, 0.52));
    this.pool.target.position.copy(aim).add(new THREE.Vector3(0.06, -0.02, 0));
    this.pool.target.updateMatrixWorld();
    this.pool.intensity = 2.6 * prog(t, T.beatAfterDown, T.beatAfterDown + 0.3);
    // the sweep: a band of light runs across each hero word left to right as it lands (0.5 s from the impact)
    const lines = [this.plus1, this.plus2];
    this.sweeps.forEach((sw, i) => {
      const l = lines[i]!, hits: [number, number][] = [[1, i === 0 ? T.memory : T.fact], [4, i === 0 ? T.commit : T.blame]];
      sw.value.w = 0;
      for (const [w, at] of hits) {
        const u = prog(t, at + 0.03, at + 0.53, ease.inOutQuad);
        if (u <= 0 || u >= 1) continue;
        const [x0, x1] = l.wordSpan(w), sz = l.solid.size;
        const origin = l.group.localToWorld(new THREE.Vector3(0, 0, 0));
        sw.value.set(origin.x + lerp(x0 - 1.0 * sz, x1 + 1.0 * sz, u) + 0.4 * origin.y, 0.35 * sz, 0.4, 2.2 * Math.sin(Math.PI * u));
      }
    });
    // the backdrop's pool follows the hero word
    const eye = this.stage.camera.position, zb = this.backdrop.mesh.position.z;
    const behind = eye.clone().lerp(aim, (zb - eye.z) / (aim.z - eye.z));
    this.backdrop.set(behind.x, behind.y, 1.1, 0.55, prog(t, T.beatAfterDown, T.beatAfterDown + 0.4));
  }

  // ---------------------------------------------------------------------------------------------- the headline

  private animateHeadline(t: number, f: Frame) {
    const T = this.T;
    this.lightHeadline(t);
    // the − line is there as we cut to it; the strike runs through it on the cut's beat
    const sk = prog(t, T.beatAfterDown + 0.03, T.beatAfterDown + 0.26, ease.outCubic);
    this.strike.visible = sk > 0;
    const [x0, x1] = [this.minus.wordSpan(0)[0] - 0.04 * EM, this.minus.wordSpan(2)[1] + 0.04 * EM];
    this.strike.scale.x = Math.max(1e-4, sk * (x1 - x0));

    this.typeLine(this.plus1, t, [T.every1, T.memory, T.has1, T.a1, T.commit]);
    this.typeLine(this.plus2, t, [T.every2, T.fact, T.has2, T.a2, T.blame]);

    // the diff glow comes up as the accent lands, flaring on the impact and settling to the film's level
    this.accent.forEach((m, i) => {
      const at = i === 0 ? T.commit : T.blame;
      m.emissiveIntensity = GLOW_LEVEL * clamp(slam(t, at + 0.05, { freq: 3 })) * (1.12 + 0.25 * pulse(t, at + 0.06, 0.2) + 0.06 * onBeat(f, 0.35));
    });

    // the blame gutter slides in at left on "blame"
    const bk = prog(t, T.blame + 0.02, T.blame + 0.45, ease.outExpo);
    this.blame.group.visible = this.blameRule.visible = bk > 0;
    this.placeBlame(bk);
    for (const mt of this.blameMats) mt.opacity = bk;
    (this.blameRule.material as THREE.MeshBasicMaterial).opacity = bk;

    // the exit: the whole headline drifts back
    this.head.position.z = -keys(t, [[T.end - 0.42, 0], [T.end, 0.38, ease.inCubic]]);
  }

  /** A + line: its mark and flat words type in on their times, its hero words slam in from depth on their onsets. */
  private typeLine(l: DiffLine, t: number, at: number[]) {
    l.mark.group.visible = t >= at[0]! - 0.04;
    l.words.forEach((gs, w) => {
      const t0 = at[w]!, hero = l.heroes.has(w);
      gs.forEach((g, k) => {
        const m = g.mesh;
        if (!hero) {
          m.visible = t >= t0 + k / 30;
          return;
        }
        const s = slam(t, t0 + 0.016 * k);
        m.visible = s > 0;
        m.position.copy(g.home);
        m.position.z += (s - 1) * 3.2 * l.solid.size;
        m.rotation.set((1 - s) * 0.6, 0, 0);
        m.scale.setScalar(l.solid.size);
      });
    });
  }

  override dispose() {
    this.thread.dispose();
    this.bead.dispose();
    this.backdrop.dispose();
    for (const l of [this.minus, this.plus1, this.plus2]) l.dispose();
    this.blame.dispose();
    this.strike.geometry.dispose();
    this.blameRule.geometry.dispose();
    for (const m of this.mats) m.dispose();
    this.stage.dispose();
  }
}

// ------------------------------------------------------------------------------------------------ timing

/** Every time the scene keys on, from the voiceover's onsets and the score's grid. */
function timesOf(vo: VO, audio: AudioData, start: number, end: number) {
  const ws = wordTimes(vo, 'her');
  const find = (w: string, nth = 0) => {
    const h = ws.filter((x) => norm(x.w.w) === w)[nth];
    if (!h) throw new Error(`her: no spoken "${w}" (#${nth})`);
    return h.at;
  };
  const not = find('not'), me = find('me');
  const down = audio.downbeats.find((d) => d > me);
  if (down === undefined) throw new Error('her: no downbeat after "me."');
  const beatAfterDown = audio.beats.find((b) => b > down + 0.05) ?? down + 60 / audio.bpm;
  const a1 = find('a', 0), a2 = find('a', 1);
  // "has" is never spoken: it types in just before her "a", or on a downbeat that falls in the pause before it (the
  // downbeat is an event)
  const hasBefore = (after: number, a: number) => audio.downbeats.find((d) => d > after + 0.2 && d < a - 0.12) ?? a - 0.13;
  const memory = find('memory'), fact = find('fact');
  return {
    start, end, not, me, down, beatAfterDown,
    every1: find('every', 0), memory, has1: hasBefore(memory, a1), a1, commit: find('commit'),
    every2: find('every', 1), fact, has2: hasBefore(fact, a2), a2, blame: find('blame'),
  };
}

/** A linear colour scaled. */
function scaled(c: readonly [number, number, number], k: number): [number, number, number] {
  return [c[0] * k, c[1] * k, c[2] * k];
}
