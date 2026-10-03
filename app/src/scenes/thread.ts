// Scene 01 `thread`: "Your agent forgets." / "Every conversation… back to zero." The film's cold open (Plan 2 Task 11;
// spec §4 01).
//
// The picture is Blender shot B01 (blender/shots/b01_thread.py): a macro of one bone 3-ply thread, 85 mm at f/1.8 on
// ink, that lights up on the first beat, pulses with the heartbeat, frays as she says "forgets" and snaps on "zero"
// in a 0.25x speed ramp, its broken ends recoiling and its own fibres drifting through the key light. This module
// composites that plate and sets the type over it, every time from the data (her measured onsets, the score's beats):
// - L01 in the lower-left third, flat Bricolage, bone at 70%: each word on its onset; as she says "forgets" its
//   tracking loosens and its letters drift apart and let go, the way the thread's fibres lift.
// - L02 above the thread, right of centre: "back to" flat, and "zero." as extruded satin-bone Type3D that slams in
//   from depth on its onset, lands as the thread snaps and cracks in two there. Each half rides one of the thread's
//   broken ends (tracked in Blender: end_l, end_r) and turns away, showing the fracture face.
// The word block hangs over the break (the track's break point at the snap), so the crack runs up from the break.
// The plate carries the slow motion; the word's own springs run on the same speed ramp (motion.speedRamp), so they
// slow with it.
import * as THREE from 'three';
import { Scene, disposeLayer, type Frame } from '../engine/scene';
import { Stage } from '../engine/stage';
import { Type3D } from '../engine/type3d';
import { Layer2D, W, H, clearRT } from '../engine/gl';
import { LIN } from '../engine/palette';
import { Plate } from '../engine/plates';
import { Track, type Anchor } from '../engine/track';
import { F } from '../engine/type';
import { slam, speedRamp } from '../engine/motion';
import type { Word } from '../engine/vo';
import { clamp, ease, keys } from '../engine/util';
import { crackMaterial, setCrack, setPose, type CrackUniforms } from './thread-crack';
import { drawLine, type WordAt } from './thread-type';
import { threadTimes } from './thread-time';
import S from './thread.strings.json';

const [L01, BACK_TO, ZERO] = S as [string, string, string];
const SHOT = 'b01_thread';

// ------------------------------------------------------------------------------------------------ layout (1080p px)

/** L01: lower-left third, inside title safe. */
const L01_X = 150, L01_Y = 866, L01_SIZE = 64;
/** L02: "back to" over "zero.", the block's crack over the thread's break. */
const BACK_SIZE = 62;
const ZERO_EM = 250; // px per em of "zero."
const ZERO_ABOVE = 168; // its baseline above the break point
const BACK_ABOVE = 186; // "back to"'s baseline above "zero."'s
/** The word turns into the thread's space: its right side away, like the thread receding. */
const ZERO_YAW = -0.2;

// ------------------------------------------------------------------------------------------------ the stage

const FOV = 24;
const DEPTH = 5; // the word's distance from the camera
const PX = H / 2 / (DEPTH * Math.tan((FOV * Math.PI) / 360)); // px per world unit at the word
const EM = ZERO_EM / PX;
/** The slam: how deep each glyph starts (em) and the stagger between glyphs (thread time, s): the last lands on the hit. */
const FLY = 3.2;
const STAGGER = 0.014;
/** Riding the recoil: how much of each broken end's motion its half takes (x, y); the ends fall away below, the
 * halves only part and dip. And how far each half turns as it goes: its fracture face comes round to the light. */
const RIDE: [number, number][] = [[0.22, 0.1], [0.22, 0.1]];
const TURN = { roll: 0.07, yaw: 0.18, back: 0.1 };

/** The word's light, like the plate's: a warm-neutral key from the upper left, a rim from behind. */
const KEY = 26, RIM = 2.8;

/** Where the crack runs (the word's x, world units): the middle of the gap between the e and the r. */
const crackRef = (line: Type3D) => {
  const r = line.glyphs.find((g) => g.ch === 'r') ?? line.glyphs[Math.floor(line.glyphs.length / 2)]!;
  return r.x + 0.01 * EM;
};

const toWorld = (x: number, y: number) => new THREE.Vector3((x - W / 2) / PX, (H / 2 - y) / PX, -DEPTH);

interface Half {
  pivot: THREE.Group;
  line: Type3D;
  mat: THREE.MeshPhysicalMaterial;
  u: CrackUniforms;
}

export default class ThreadScene extends Scene {
  private plate!: Plate;
  private track!: Track;
  private layer = new Layer2D();
  private stage!: Stage;
  private halves: Half[] = [];
  private words!: Record<string, Word>;
  private ramp: [number, number][] = [];
  /** Thread time of the snap (the "zero." onset through the ramp), and film time of the last whole frame before it. */
  private snapTau = 0;
  private preSnap = 0;
  private breakAt!: Anchor;
  private base = new THREE.Vector3();
  private lightOn = 0;
  private key!: THREE.SpotLight;
  private rim!: THREE.DirectionalLight;

  override async init() {
    this.track = await Track.load(SHOT);
    this.plate = new Plate(SHOT, this.track.f0, { count: this.track.frames });

    // every time from thread-time.ts: the words, the plate's speed ramp, the light, the snap
    const T = threadTimes(this.ctx.vo, this.ctx.audio, this.ctx.start, this.ctx.end);
    this.words = T.words;
    this.ramp = T.ramp;
    this.snapTau = this.tau(T.snap);
    this.lightOn = T.lightOn;
    // the break point: where both ends are on the last frame before the snap
    this.preSnap = T.preSnap;
    this.breakAt = this.track.at('end_l', this.preSnap);

    // the stage: the word hangs over the break, lit like the plate (warm-neutral key from the upper left, rim behind)
    const st = (this.stage = new Stage(this.ctx.renderer, { fov: FOV }));
    st.camera.position.set(0, 0, 0);
    st.camera.lookAt(0, 0, -1);
    // the key is a soft spot high on the left, close enough that its light falls off across the word
    const key = new THREE.SpotLight(new THREE.Color().setRGB(1, 0.93, 0.86), KEY, 0, 0.5, 0.9, 2);
    key.position.set(-1.4, 2.4, -2.4);
    const rim = new THREE.DirectionalLight(0xffffff, RIM);
    rim.position.set(2.4, 3.2, -4);
    const fill = new THREE.DirectionalLight(0xffffff, 0.25);
    fill.position.set(3, -1, 2);
    this.key = key;
    this.rim = rim;
    for (const l of [key, rim, fill]) {
      l.target.position.set(0, 0, -DEPTH);
      st.scene.add(l, l.target);
    }

    const fam = F.display(100, 600);
    for (const side of [-1, 1] as const) {
      const { mat, u } = crackMaterial(side);
      const line = new Type3D(ZERO, { family: fam, size: EM }, mat);
      const pivot = new THREE.Group();
      // the crack runs down between the e and the r: the pivot sits on it, on the baseline
      const crackX = crackRef(line);
      line.group.position.x = -crackX;
      setCrack(u, crackX, EM);
      pivot.add(line.group);
      st.scene.add(pivot);
      this.halves.push({ pivot, line, mat, u });
    }
    this.base = toWorld(this.breakAt.x, this.breakAt.y - ZERO_ABOVE);
  }

  override async prepare(t: number) {
    await this.plate.prepare(t);
  }

  /** The thread's own time at film time t (the plate's speed ramp). */
  private tau(t: number) {
    return this.ctx.start + speedRamp(t - this.ctx.start, this.ramp);
  }

  render(f: Frame, out: THREE.WebGLRenderTarget) {
    const { renderer, comp } = this.ctx;
    const t = f.t, w = this.words as Record<string, Word>;
    clearRT(renderer, out, LIN.ink);
    // black until the light comes on (the plate's thread is there, unlit: a dark line on ink)
    const on = clamp((t - this.lightOn) / 0.05);
    if (on > 0) this.plate.draw(renderer, comp, out, t, { mode: 'normal', opacity: on });

    // ---- flat type
    const L = this.layer, c = L.ctx;
    L.clear();
    const fam = F.display(100, 500);
    const l01: WordAt[] = L01.split(' ').map((text, i) => {
      const wd = [w.your!, w.agent!, w.forgets!][i]!;
      return { text, at: wd.start, end: wd.end };
    });
    const fEnd = w.forgets!.end;
    drawLine(c, t, l01, fam, L01_SIZE, L01_X, L01_Y, { loosen: 2, gone: fEnd + 0.62, fadeFrom: fEnd + 0.1, fadeTo: fEnd + 0.62 });

    // "back to" over "zero.", left-aligned with its z
    const z0 = this.halves[0]!.line;
    const zLeft = this.breakAt.x - crackRef(z0) * PX;
    const backWords: WordAt[] = BACK_TO.split(' ').map((text, i) => {
      const wd = [w.back!, w.to!][i]!;
      return { text, at: wd.start, end: wd.end };
    });
    drawLine(c, t, backWords, fam, BACK_SIZE, zLeft + 0.04 * ZERO_EM, this.breakAt.y - ZERO_ABOVE - BACK_ABOVE);
    comp.draw(renderer, L.upload(), out);

    // ---- "zero.": slams in on its onset (through the ramp), cracks in two as the thread snaps
    const tau = this.tau(t);
    if (tau < this.snapTau - 0.4) return;
    const st = this.stage;
    const n = z0.glyphs.length;
    const dl = this.ride('end_l', t), dr = this.ride('end_r', t);
    this.halves.forEach((h, hi) => {
      h.line.glyphs.forEach((g, k) => {
        const s = slam(tau, this.snapTau - (n - 1 - k) * STAGGER);
        g.mesh.visible = s > 0;
        g.mesh.position.copy(g.home);
        g.mesh.position.z += (s - 1) * FLY * EM;
        g.mesh.rotation.set((1 - s) * 0.5, 0, 0);
        g.mesh.scale.setScalar(h.line.size);
      });
      const d = hi === 0 ? dl : dr, sgn = hi === 0 ? 1 : -1; // the left half rolls anticlockwise, the right clockwise
      const p = clamp(Math.hypot(d.x, d.y) / 260);
      const [rx, ry] = RIDE[hi]!;
      h.pivot.position.copy(this.base).add(new THREE.Vector3((rx * d.x) / PX, (-ry * d.y) / PX, -TURN.back * p * (hi === 0 ? 0.6 : 1)));
      // each half turns its cut face towards the camera (the left half's faces +x, the right half's -x)
      h.pivot.rotation.set(0.05 * p, ZERO_YAW - sgn * TURN.yaw * p, sgn * TURN.roll * p);
      setPose(h.u, h.line.group, st.camera);
    });
    // the plate's light at the snap: the key dips and the rim flares (b01_thread.py), on the word too
    const hit = tau > this.snapTau ? THREE.MathUtils.smoothstep(tau - this.snapTau, 0, 0.03) : 0;
    this.key.intensity = KEY * (1 - 0.45 * hit);
    this.rim.intensity = RIM * (1 + 0.8 * hit);
    // a specular sweep crosses the satin as it lands
    st.scene.environmentRotation.set(0, keys(tau, [[this.snapTau - 0.1, -1.1], [this.snapTau + 0.3, 0.9, ease.outCubic]]), 0);
    st.render(out, { clear: false });
  }

  /** How far a broken end has moved from the break (px): 0 until the snap, so until then the two halves are posed
   * exactly alike and make one seamless word (the break point itself drifts with the pulse and the camera). */
  private ride(name: string, t: number) {
    if (t <= this.preSnap) return { x: 0, y: 0 };
    const a = this.track.at(name, t);
    return { x: a.x - this.breakAt.x, y: a.y - this.breakAt.y };
  }

  override dispose() {
    this.plate?.dispose();
    disposeLayer(this.layer);
    for (const h of this.halves) {
      h.line.dispose();
      h.mat.dispose();
    }
    this.stage?.dispose();
  }
}

