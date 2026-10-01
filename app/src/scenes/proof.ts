// Scene 12 `proof`: "Forty-four… to ninety-one point four." / "Not bad… for a memory." (Plan 2 Task 22; spec §4 12.)
// The film's flex: a product launch's money number.
//
// One world, every time from the data (her measured onsets, the score's section, beats and downbeats; proof-time.ts):
// 1. The dark. The cut lands in the room tone `honest` left: a huge odometer of extruded Bricolage drums (proof-drums.ts)
//    stands in the dark, seen close from the right, only a rim of light on the walls of its 44. As she says
//    "Forty-four…" a narrow band of light glints across it and its faces come up out of the dark.
// 2. The slam. The score comes back on the downbeat and the drums are kicked: the lights slam on, the camera snaps back
//    and round to a low wide shot, and the odometer rolls one round a beat (proof-count.ts), each kicked on its beat and
//    clicking home on the "and": 44 → 72 → 80 → 83. The drums count as a real odometer's do, the ones drum spinning, the
//    tens ticking over as it passes 9 (80 → 83 is three slow steps: a small gain looks small), the two opening to a
//    tabular gap as they turn and closing to each figure's kerning as they land. Beside the figure the sparkline climbs
//    with them, a moss light at its head writing each climb, the round's tag lighting under its node (proof-board.ts).
// 3. The landing. On the last round the chart drops away under where the decimal will stand, the tenths drum spins in
//    with the point, and the camera pushes in; as she says "four." 91.4 clicks home in moss (the diff glow on every
//    edge) and a band of light runs across it.
// 4. The proof. On the next downbeat the camera pulls back to the board and the six per-category bars flash in under the
//    figure, a 64th note apart, the source typing under them, the chart now under the figure's right. The `%` is the
//    last drum: on "bad" it flips up into the window with a tiny smirk of a bounce. The quote types in on the next beat,
//    the moss breathes on the beats, the camera drifts in and round, and a last band of light crosses 91.4% on the
//    scene's last downbeat.
import * as THREE from 'three';
import { Scene, type Frame, type PostOverrides } from '../engine/scene';
import { CameraRig, Stage, initAreaLights } from '../engine/stage';
import { H, W, makeRT } from '../engine/gl';
import { Mat } from '../engine/type3d';
import { F, layout } from '../engine/type';
import { LIN } from '../engine/palette';
import { GLOW_LEVEL } from '../engine/look';
import { onBeat, slam } from '../engine/motion';
import { sweepAt, withSweep, type SweepBand } from '../engine/sweep';
import { clamp, ease, keys, lerp, prog, pulse } from '../engine/util';
import { timesOf, type Times } from './proof-time';
import { drumsAt, rollEase, roundsOf, type Round } from './proof-count';
import { CENTRE, DIGITS, Drum, withWindow } from './proof-drums';
import { Board } from './proof-board';
import { box, fitKey } from './proof-camera';
import S from './proof.strings.json';

// ------------------------------------------------------------------------------------------------ the copy

const COPY = S as string[];
/** The rounds: v1 44, v3 72, v4 80, v5 83, v7 91.4%. */
export const ROUNDS: Round[] = roundsOf(COPY.slice(0, 10));
const FINAL = ROUNDS[ROUNDS.length - 1]!;
/** The v7 bars: each "label score" split at its last space. */
export const BARS = COPY.slice(10, 16).map((s) => ({ label: s.slice(0, s.lastIndexOf(' ')), value: s.slice(s.lastIndexOf(' ') + 1) }));
const NOTES = [COPY[16]!, COPY[17]!] as const;

// ------------------------------------------------------------------------------------------------ the world (metres)

/** World units per em of the figure: a figure 7 cm tall, a desk-sized counter seen through a macro lens. */
const EM = 0.1;
/** The figure's face: Bricolage at full width, heavy. */
const FAMILY = F.display(100, 800);
/** While they turn, the tens and ones drums stand at least this far apart (em): the widest figures' advance, so two
 * wide digits never cross ("91" is kerned 0.45 em apart, a turning 0 is 0.59 em wide). */
const TAB = 0.62;
/** The lens and its stops: wide open and sultry in the dark, stopped down for the board. */
const FOV = 24;
const STOPS = { dark: 2.4, roll: 3.6, final: 6.3 };
const INK = new THREE.Color().setRGB(...LIN.ink);

/** The %'s smirk on "bad": a hop (em) and a rock of its head (rad), each a damped ring of the house's springiness. */
const SMIRK = { hop: 0.045, rock: 0.11, freq: 4.5, rockFreq: 4, damping: 0.55 };

/** An impulse's ring: 0 before dt = 0, then a damped sine rising first, `amp` its envelope. */
function ring(dt: number, amp: number, freq: number, damping: number): number {
  if (dt <= 0) return 0;
  const w = 2 * Math.PI * freq;
  return amp * Math.exp(-damping * w * dt) * Math.sin(w * Math.sqrt(1 - damping * damping) * dt);
}

/** The drums, left to right: tens, ones, the point, tenths, the percent sign. */
const D = { TENS: 0, ONES: 1, DOT: 2, TENTHS: 3, PCT: 4 } as const;

export default class Proof extends Scene {
  private T!: Times;
  private stage!: Stage;
  private counter = new THREE.Group();
  private drums: Drum[] = [];
  private presence: THREE.IUniform<number>[] = [];
  private mats: THREE.MeshPhysicalMaterial[] = [];
  private sweep!: SweepBand;
  private board!: Board;
  private backdrop!: Backdrop;
  private rig!: CameraRig;
  /** Each round's drum centres (em from the figure's origin), the drums a figure leaves out chained on at the last
   * figure's spacing. */
  private spots: number[][] = [];
  /** Each round's figure width (em), and the last figure's before its % lands. */
  private widths: number[] = [];
  private bare = 0;
  private lights!: { top: THREE.RectAreaLight; key: THREE.DirectionalLight; rim: THREE.DirectionalLight; pool: THREE.SpotLight };

  override init() {
    const { renderer, vo, audio, start, end } = this.ctx;
    this.T = timesOf(vo, audio, start, end);
    this.stage = new Stage(renderer, { fov: FOV, near: 0.02, far: 20 });
    this.buildCounter();
    this.board = new Board(EM, ROUNDS, BARS, NOTES, this.widths[this.widths.length - 1]!);
    this.counter.add(this.board.group);
    this.stage.scene.add(this.counter);
    this.backdrop = new Backdrop(LIN.ink, LIN.panel, [9, 5]);
    this.backdrop.mesh.position.set(0.13, 0, -1.1);
    this.stage.scene.add(this.backdrop.mesh);
    this.buildLights();
    this.buildRig();
    this.warmUp();
  }

  // ---------------------------------------------------------------------------------------------- build

  private buildCounter() {
    const addDrum = (slots: readonly string[]) => {
      const m = Mat.accent('moss', 0);
      const band = withSweep(m);
      if (this.sweep) band.value = this.sweep.value; // one band across the whole figure
      else this.sweep = band;
      this.mats.push(m);
      const d = new Drum(slots, FAMILY, EM, m);
      this.presence.push(withWindow(m, d.win)); // each drum's own window
      this.counter.add(d.group);
      this.drums.push(d);
    };
    const mark = (c: string) => [c, ...Array<string>(9).fill('')];
    addDrum(DIGITS);
    addDrum(DIGITS);
    addDrum(mark('.'));
    addDrum(DIGITS);
    addDrum(mark('%'));
    // each round's figure as one kerned line: its glyphs' centres (em), then the drums it leaves out, chained on
    const lay = (s: string) => layout(s, FAMILY, 1000);
    const centres = (s: string) => lay(s).glyphs.map((g) => (g.x + g.w / 2) / 1000);
    const fin = centres(FINAL.figure);
    this.spots = ROUNDS.map((r) => {
      const c = centres(r.figure);
      for (let j = c.length; j < fin.length; j++) c.push(c[j - 1]! + fin[j]! - fin[j - 1]!);
      return c;
    });
    this.widths = ROUNDS.map((r) => lay(r.figure).width / 1000);
    this.bare = lay(FINAL.figure.replace('%', '')).width / 1000;
  }

  private buildLights() {
    const s = this.stage.scene;
    // neutral light only (lit bone stays out of the bloom's chroma gate): a long softbox above whose reflection runs
    // along the top bevels, a raking spot on the figure from the upper left (the faces fall off across it, the walls
    // model), a low key, and a hard rim from behind on the right that draws the edges out of the dark
    initAreaLights();
    const top = new THREE.RectAreaLight(0xffffff, 0, 0.9, 0.16);
    top.position.set(0.14, 0.32, 0.2);
    top.lookAt(0.14, 0.03, -0.02);
    const key = new THREE.DirectionalLight(0xffffff, 0);
    key.position.set(-1.4, 2.2, 1.8);
    key.target.position.set(0.12, 0, -0.1);
    const rim = new THREE.DirectionalLight(0xffffff, 0);
    rim.position.set(1.6, 1.4, -2.4);
    rim.target.position.set(0.12, 0, -0.1);
    const pool = new THREE.SpotLight(0xffffff, 0, 0, THREE.MathUtils.degToRad(11), 1, 2);
    s.add(top, key, key.target, rim, rim.target, pool, pool.target);
    this.lights = { top, key, rim, pool };
  }

  /** The figure of round r, boxed (em: cap height and a hair under the baseline). */
  private figBox(r: number) {
    return box(0, this.widths[r]!, -0.03, 0.69, EM);
  }

  private buildRig() {
    const T = this.T, L = this.board.L, W4 = this.widths[4]!;
    // the rolls: the figure with the line climbing under it; the money number with its rule; the whole board
    const rolls = (r: number) => [...this.figBox(r), ...box(L.spark.x0 - 0.06, L.spark.x1 + 0.06, L.rule.y - 0.03, 0.69, EM)];
    // (91.4 alone: the % comes later, and the camera makes room for it as it pulls back to the board)
    const money = box(0, this.bare, L.rule.y - 0.03, 0.69, EM);
    const all = box(0, W4, L.notes.y2 - 0.06, 0.69, EM);
    this.rig = new CameraRig([
      // the dark: close and low on the 44, from the right, pushing in slowly through "Forty-four…"
      fitKey(T.start, this.figBox(0), { az: 28, el: 7, fov: FOV, margin: [0.22, 0.32], bias: [-0.06, 0.02] }),
      fitKey(T.slam - 0.02, this.figBox(0), { az: 22, el: 4.5, fov: FOV, margin: [0.13, 0.2], bias: [-0.06, 0.02] }, ease.linear),
      // the slam: the camera snaps back and round to the left, low, the figure looming with its chart beside it
      fitKey(T.slam + 0.18, rolls(1), { az: -13, el: -5, fov: FOV, margin: [0.1, 0.2], bias: [0, -0.04] }, ease.outExpo),
      // the rolls: drifting round toward square
      fitKey(T.kicks[3]! - 0.02, rolls(3), { az: -8, el: -3, fov: FOV, margin: [0.1, 0.2], bias: [0, -0.04] }, ease.linear),
      // the last round: the chart drops away and the camera pushes in on the money number, landing as it does
      fitKey(T.lands[3]! + 0.06, money, { az: -12, el: 3.5, fov: FOV, margin: [0.13, 0.3], bias: [0, 0.06] }, ease.outCubic),
      fitKey(T.bars - 0.02, money, { az: -13.5, el: 4, fov: FOV, margin: [0.12, 0.29], bias: [0, 0.06] }, ease.linear),
      // the proof: back again on the downbeat to the whole board, then drifting in and round, title-safe at the end
      fitKey(T.bars + 0.32, all, { az: -11, el: 6, fov: FOV, margin: [0.13, 0.23], bias: [0, 0] }, ease.outCubic),
      fitKey(T.end, all, { az: -14, el: 6.5, fov: FOV, margin: [0.11, 0.19], bias: [0, 0] }, ease.inOutQuad),
    ]);
  }

  /**
   * Draw everything once at full size before the first frame: shaders compile for the stage's target and the geometry
   * uploads, so no first-use stall lands on a frame. Nothing it sets outlives it: render() sets all state from t.
   */
  private warmUp() {
    const st = this.stage, rt = makeRT(W, H);
    const culled: THREE.Object3D[] = [];
    st.scene.traverse((o) => {
      if (o.frustumCulled) (o.frustumCulled = false), culled.push(o);
    });
    this.board.group.traverse((o) => (o.visible = true));
    for (const p of this.presence) p.value = 1;
    this.rig.apply(st.camera, this.T.end);
    st.compile();
    st.render(rt, { dof: { focus: 0.6, fstop: 4 } });
    for (const o of culled) o.frustumCulled = true;
    rt.dispose();
  }

  // ---------------------------------------------------------------------------------------------- render

  render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides {
    const t = f.t, T = this.T, st = this.stage;
    const c = drumsAt(t, ROUNDS, T.kicks, T.lands);
    this.poseCounter(t, c, f);
    this.board.update(t, {
      first: T.slam - 0.02, rule: T.slam, drop: [T.kicks[3]! - 0.12, T.kicks[3]! + 0.32], kicks: T.kicks, lands: T.lands,
      bars: T.bars, note1: T.bars + 0.12, note2: T.quote,
    }, c.round, rollEase(c.u), T.beat);
    this.rig.apply(st.camera, t);
    this.light(t, c.round);

    // each drum's window, where the drum stands now
    for (const d of this.drums) d.frame();

    const r = this.ctx.renderer, cc = r.getClearColor(new THREE.Color()), ca = r.getClearAlpha();
    r.setClearColor(INK, 1);
    st.render(out, { dof: this.focus(t) });
    r.setClearColor(cc, ca);

    // the slam jolts the frame and punches in; each kick and the landings a hair
    let shake = 0, zoom = 0;
    T.kicks.forEach((k, i) => {
      if (t < k) return;
      const dt = t - k, a = i === 0 ? 6 : 2.2;
      shake += a * Math.exp(-dt * 18) * Math.cos(dt * 2 * Math.PI * 10);
      zoom += (i === 0 ? 0.022 : 0.007) * pulse(t, k, i === 0 ? 0.14 : 0.08);
    });
    zoom += 0.009 * pulse(t, T.lands[3]!, 0.1) + 0.006 * pulse(t, T.bars, 0.1) + 0.004 * pulse(t, T.bad, 0.08);
    return { shake: [0, shake], zoom: 1 + zoom };
  }

  /** The drums: turned to the count, standing at the figure's kerning, loosened while they turn. */
  private poseCounter(t: number, c: ReturnType<typeof drumsAt>, f: Frame) {
    const T = this.T;
    const prev = this.spots[Math.max(0, c.round - 1)]!, next = this.spots[c.round]!;
    let x = lerp(prev[0]!, next[0]!, c.kern);
    this.drums.forEach((d, j) => {
      if (j > 0) {
        const gap = lerp(prev[j]! - prev[j - 1]!, next[j]! - next[j - 1]!, c.kern);
        x += j === D.ONES ? lerp(gap, Math.max(gap, TAB), c.loose) : gap;
      }
      d.at(x * EM);
    });
    this.drums[D.TENS]!.turn(c.tens);
    this.drums[D.ONES]!.turn(c.ones);
    this.drums[D.TENTHS]!.turn(c.tenths);
    const last = T.kicks[3]!, land = T.lands[3]!;
    // the point rolls up into the window as the tenths drum slows (a spring whose overshoot turns it toward the window's
    // middle, never out of it)
    this.drums[D.DOT]!.turn(-1 + slam(t, land - 0.05, { freq: 5, damping: 0.62 }));
    // the % is the last drum: it flips up into the window on "bad", its wheel landing dead (a turn past would carry its
    // top into the window's fade), and the smirk is the drum's own: a tiny hop and a rock of its head, its window riding
    // with it
    const pct = this.drums[D.PCT]!, dt = t - T.bad;
    pct.turn(-1 + prog(t, T.bad - 0.1, T.bad + 0.02, ease.outCubic));
    pct.group.position.y = (CENTRE + ring(dt - 0.02, SMIRK.hop, SMIRK.freq, SMIRK.damping)) * EM;
    pct.group.rotation.z = -ring(dt - 0.03, SMIRK.rock, SMIRK.rockFreq, SMIRK.damping);
    this.presence[D.TENS]!.value = this.presence[D.ONES]!.value = 1;
    this.presence[D.DOT]!.value = this.presence[D.TENTHS]!.value = prog(t, last + 0.04, last + 0.1);
    this.presence[D.PCT]!.value = t > last ? 1 : 0;
    // the moss: lit as 91.4 lands, a flare settling to the film's level, breathing a hair on the beats after
    const breath = t > T.bars - 0.05 ? 0.07 * onBeat(f, 0.3) : 0;
    const g = GLOW_LEVEL * clamp(slam(t, land + 0.02, { freq: 3 })) * (1.12 + 0.2 * pulse(t, land + 0.03, 0.22) + breath);
    for (const m of this.mats) m.emissiveIntensity = g;
  }

  /** The lights: dark but for a rim, the reveal on "Forty-four…", everything on at the slam; the sweeps. */
  private light(t: number, round: number) {
    const T = this.T, Lt = this.lights;
    const reveal = prog(t, T.forty - 0.05, T.forty + 0.7, ease.outCubic);
    const on = t >= T.slam ? 1 : 0;
    // each kick flares the rim (the drums tearing into motion catch it)
    const kick = Math.max(...T.kicks.map((k) => pulse(t, k, 0.12)));
    // (in the dark the faces stay near black: bone takes any fill as grey plastic, so only the rim and the sweep's
    // glint on the bevels draw the 44, and a faint top light gives its faces a breath of form)
    Lt.rim.intensity = lerp(lerp(1.1, 1.5, reveal), 2.4, on) * (1 + 0.5 * kick);
    Lt.top.intensity = lerp(lerp(0, 0.16, reveal), 2.8, on);
    Lt.key.intensity = lerp(0, 0.14, on);
    this.stage.scene.environmentIntensity = lerp(lerp(0.012, 0.03, reveal), 0.13, on);
    // the pool: a narrow raking spot from the upper left on the figure's left side, so its faces fall off to the right
    const w = this.widths[Math.min(round, this.widths.length - 1)]!;
    const aim = new THREE.Vector3(0.32 * w * EM, CENTRE * EM, 0);
    Lt.pool.position.copy(aim).add(new THREE.Vector3(-0.4, 0.36, 0.5));
    Lt.pool.target.position.copy(aim).add(new THREE.Vector3(0.04, -0.02, 0));
    Lt.pool.target.updateMatrixWorld();
    Lt.pool.intensity = lerp(lerp(0, 0.16, reveal), 2.4, on);
    // the backdrop lifts behind the figure with the light
    this.backdrop.set((w / 2) * EM, CENTRE * EM, 0.9, 0.42, lerp(0.3 * reveal, 1, on));
    // the sweeps: the reveal across the 44 as she says it, a narrow glint in the dark; across 91.4 as it lands
    const w0 = this.widths[0]!, w4 = this.widths[4]!, land = T.lands[3]!;
    if (t < T.slam) sweepAt(this.sweep, t, [{ t0: T.forty, t1: T.forty + 1.1, x0: -0.4 * EM, x1: (w0 + 0.4) * EM, y: 0 }], { width: 0.2 * EM, strength: 4 });
    else {
      // and a last shine across 91.4% on the scene's last downbeat, before the cut
      const passes = [{ t0: land + 0.03, t1: land + 0.62, x0: -0.4 * EM, x1: (w4 + 0.4) * EM, y: 0 }];
      if (T.shine !== null) passes.push({ t0: T.shine + 0.02, t1: T.shine + 0.58, x0: -0.4 * EM, x1: (w4 + 0.4) * EM, y: 0 });
      sweepAt(this.sweep, t, passes, { width: 0.36 * EM });
    }
  }

  /** Focus, in diopters as a focus ring turns, and the stop: the 44's first digit, the figure, the board. */
  private focus(t: number) {
    const T = this.T, st = this.stage;
    const inv = (x: number, y: number) => 1 / Math.max(0.03, st.depthOf([x * EM, y * EM, 0]));
    const fig = (r: number) => inv(this.widths[r]! / 2, CENTRE);
    const D = keys(t, [
      [T.start, inv(this.spots[0]![0]!, CENTRE)],
      [T.slam - 0.02, inv(this.spots[0]![0]!, CENTRE)],
      [T.slam + 0.12, fig(1), ease.outCubic],
      [T.kicks[3]!, fig(3), ease.linear],
      [T.lands[3]! + 0.06, fig(4), ease.inOutCubic],
      [T.bars, fig(4)],
      [T.bars + 0.32, inv(this.widths[4]! / 2, -0.2), ease.inOutCubic],
      [T.end, inv(this.widths[4]! / 2, -0.2)],
    ]);
    const fstop = keys(t, [[T.slam - 0.01, STOPS.dark], [T.slam, STOPS.roll, ease.linear], [T.kicks[3]!, STOPS.roll], [T.lands[3]! + 0.1, STOPS.final, ease.inOutCubic]]);
    return { focus: 1 / D, fstop };
  }

  override dispose() {
    for (const d of this.drums) d.dispose();
    for (const m of this.mats) m.dispose();
    this.board?.dispose();
    this.backdrop?.dispose();
    this.stage?.dispose();
  }
}

/**
 * The dark studio behind the counter: a wide plane far back whose ink lifts, very softly, toward `lift` in a pool behind
 * the figure, as a key's spill falls on a backdrop. Unlit and opaque (the depth of field reads it as the far distance).
 */
class Backdrop {
  mesh: THREE.Mesh;
  private u: { uInk: THREE.IUniform<THREE.Vector3>; uLift: THREE.IUniform<THREE.Vector3>; uCentre: THREE.IUniform<THREE.Vector2>; uRadius: THREE.IUniform<THREE.Vector2>; uLevel: THREE.IUniform<number> };

  constructor(ink: readonly [number, number, number], lift: readonly [number, number, number], size: [number, number]) {
    this.u = {
      uInk: { value: new THREE.Vector3(...ink) },
      uLift: { value: new THREE.Vector3(...lift) },
      uCentre: { value: new THREE.Vector2() },
      uRadius: { value: new THREE.Vector2(1, 0.5) },
      uLevel: { value: 0 },
    };
    const mat = new THREE.ShaderMaterial({
      uniforms: this.u,
      vertexShader: /* glsl */ `varying vec3 vW; void main() { vW = (modelMatrix * vec4(position, 1.0)).xyz; gl_Position = projectionMatrix * viewMatrix * vec4(vW, 1.0); }`,
      fragmentShader: /* glsl */ `uniform vec3 uInk, uLift; uniform vec2 uCentre, uRadius; uniform float uLevel; varying vec3 vW;
        void main() { vec2 d = (vW.xy - uCentre) / uRadius; gl_FragColor = vec4(mix(uInk, uLift, uLevel * exp(-dot(d, d))), 1.0); }`,
    });
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry(size[0], size[1]), mat);
  }

  set(cx: number, cy: number, rx: number, ry: number, level: number) {
    this.u.uCentre.value.set(cx, cy);
    this.u.uRadius.value.set(rx, ry);
    this.u.uLevel.value = level;
  }

  dispose() {
    this.mesh.geometry.dispose();
    (this.mesh.material as THREE.Material).dispose();
  }
}
